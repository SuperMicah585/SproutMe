from flask import Flask, request, jsonify, Response
import pytz
import re
import hashlib
import os
from pathlib import Path
import json
import base64
import subprocess
import sys
import threading
#from apscheduler.schedulers.background import BackgroundScheduler
#from apscheduler.triggers.cron import CronTrigger
from datetime import date, datetime, timezone
import logging
import time
from services.database_service import DatabaseHandler
from services.public_api import register_public_api, sanitize_event
from services.sitemap import register_sitemaps
from services.scraping_service import EventScraper
from services.show_health import annotate_events
from services.sms_agent import SmsAgent
from services.spotify_service import SpotifyCatalog
from services.verify_number import TwilioVerificationManager
from services.mcp_auth import issue_session
from flask_cors import CORS,cross_origin
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse
# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _load_extra_env():
    """Load local/.env files without overriding real process env (Railway/PA)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(override=False)
    except ImportError:
        pass
    roots = [
        Path(__file__).resolve().parent / ".env",
        Path("/home/phelpsm4/sproutMe/.env"),
        Path("/home/phelpsm4/sproutMe/spotify.env"),
        Path("/home/phelpsm4/sproutMe/places.env"),
    ]
    for path in roots:
        try:
            with open(path, encoding="utf-8") as handle:
                for raw in handle:
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    if key and not os.environ.get(key):
                        os.environ[key] = value
        except OSError:
            continue


_load_extra_env()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": ["https://sproutme-please.com","https://sproutme-production.up.railway.app", "http://localhost:5173", "http://127.0.0.1:5173", "https://a621-2601-602-8983-6f70-5d4e-8463-65ae-dc3c.ngrok-free.app"]}})
app.config['CORS_HEADERS'] = 'Content-Type'
# This is the function that will run every week at 9am Pacific time
'''
def weekly_task():
    # Get current time for logging
    pacific_tz = pytz.timezone('US/Pacific')
    current_time = datetime.now(pacific_tz)
    
    logger.info(f"Running weekly task at {current_time}")
    
    # Add your actual task logic here
    # For example:
    # - Data processing
    # - Sending reports
    # - Database maintenance
    # - External API calls

    
    logger.info("Weekly task completed")

# Set up the scheduler
scheduler = BackgroundScheduler()

scheduler.add_job(
    weekly_task,
    trigger=CronTrigger(
        day_of_week='mon',  # Run on Mondays (0=Monday in APScheduler)
        hour=9,             # 9 AM
        minute=0,           # At minute 0
        timezone=pytz.timezone('US/Pacific')  # Pacific timezone
    ),
    id='weekly_task_job',
    name='Run task every Monday at 9am Pacific',
    replace_existing=True
)

# For testing: Run every minute instead of weekly
scheduler.add_job(
    weekly_task,
    trigger=CronTrigger(
        minute='*',  # Run every minute
        timezone=pytz.timezone('US/Pacific')
    ),
    id='weekly_task_job',
    name='Test run every minute',
    replace_existing=True
)

# Start the scheduler
scheduler.start()
logger.info("Scheduler started")

'''

# Function to hash a phone number consistently with the client-side hashing
def hash_phone_number(phone_number):
    return hashlib.sha256(phone_number.encode()).hexdigest()

# Function to find a phone number that matches a given hash
def find_phone_by_hash(db_handler, phone_hash):
    # Create a specific handler for the user table
    user_db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="user_table"
    )
    
    # Get all phone numbers from your database
    all_phone_numbers = user_db_handler.get_all_phone_numbers()
    print(f"Searching for hash match: {phone_hash}")
    
    for phone in all_phone_numbers.get("data", []):
        calculated_hash = hash_phone_number(phone)
        print(f"Checking: {phone} -> {calculated_hash}")
        if calculated_hash == phone_hash:
            print(f"Found match: {phone}")
            return phone
    
    print("No match found for hash")
    return None

def pa_db(table_name):
    return DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name=table_name
    )

def normalize_raw_date(raw_date):
    if not raw_date:
        return ""
    if len(raw_date) == 10 and raw_date[4] == '-' and raw_date[7] == '-':
        return raw_date.replace('-', '/')
    return raw_date

def extract_city(venue):
    if not venue:
        return ""
    match = re.search(r'\(([^)]+)\)\s*$', venue)
    return match.group(1).strip() if match else ""

def event_match_key(event):
    return (
        (event.get('event_name') or '').strip(),
        (event.get('venue') or '').strip(),
        (event.get('raw_date') or event.get('date') or '').strip(),
    )

def merge_scraped_and_user_events(scraped_events, user_events):
    combined = []
    seen = set()
    for event in user_events:
        tagged = {**event, 'user_submitted': True}
        combined.append(tagged)
        seen.add(event_match_key(tagged))
    for event in scraped_events:
        key = event_match_key(event)
        if key in seen:
            continue
        combined.append(event)
    return combined

def attach_show_health(events):
    return annotate_events(
        events,
        list_heat=lambda: pa_db("artist_heat_cache")._fetch_all_rows("artist_heat_cache"),
        list_venues=lambda: pa_db("venue_place_cache")._fetch_all_rows("venue_place_cache"),
    )

def with_show_health(result):
    if isinstance(result, dict) and result.get("success") and result.get("data") is not None:
        result["data"] = attach_show_health(result.get("data") or [])
    return result

def create_user_submitted_event(data):
    event_name = (data.get('event_name') or '').strip()
    venue = (data.get('venue') or '').strip()
    raw_date = normalize_raw_date((data.get('raw_date') or data.get('date') or '').strip())

    if not event_name or not venue or not raw_date:
        return {
            "success": False,
            "message": "event_name, venue, and date are required",
            "data": None
        }, 400

    city = (data.get('city') or '').strip() or extract_city(venue)
    event_url = (data.get('event_url') or '').strip()
    payload = {
        "event_name": event_name,
        "date": (data.get('date') or '').strip(),
        "raw_date": raw_date,
        "venue": venue,
        "city": city,
        "genre": (data.get('genre') or '').strip(),
        "ticket_info": (data.get('ticket_info') or '').strip(),
        "organizer": (data.get('organizer') or '').strip(),
        "event_url": event_url,
        "event_link_url": event_url,
        "event_link_text": "Event Link" if event_url else "",
    }
    result = pa_db('user_submitted_events').add_user_submitted_event(payload)
    status = 201 if result.get('success') else 400
    if result.get('success') and result.get('data'):
        result['data']['user_submitted'] = True
    return result, status

SMS_EVENT_COLUMNS = (
    "id,event_name,headliner,date,raw_date,venue,city,genre,ticket_info,organizer,"
    "event_url,event_link_url"
)
SMS_VENUE_COLUMNS = (
    "place_id,venue_key,venue,city,display_name,rating,user_rating_count,"
    "review_summary,editorial_summary,reviews,types,lat,lng"
)
SMS_HEAT_COLUMNS = "artist_key,display_name,query,popularity,followers,rise_score"
SMS_WORKER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sms_worker.py")
SMS_WORKER_LOG = "/tmp/sproutme_sms_worker.log"
# uWSGI sets sys.executable to uwsgi itself — never use that to spawn workers.
SMS_PYTHON = os.environ.get("SMS_PYTHON") or next(
    (
        path for path in (
            "/usr/local/bin/python3.10",
            "/usr/bin/python3.10",
            "/usr/local/bin/python3",
            "/usr/bin/python3",
        )
        if os.path.isfile(path)
    ),
    "python3.10",
)

def public_list_events(columns="*"):
    scraped_result = pa_db('Events_table').get_all_events(columns=columns)
    user_result = pa_db('user_submitted_events').get_user_submitted_events()
    return merge_scraped_and_user_events(
        scraped_result.get('data') or [],
        user_result.get('data') or [],
    )

def public_list_events_annotated(columns=None):
    cols = columns or (
        "id,event_name,headliner,date,raw_date,venue,city,genre,ticket_info,organizer,event_url"
    )
    return attach_show_health(public_list_events(columns=cols))

def public_get_event(event_id):
    try:
        user_response = pa_db('user_submitted_events').client.table('user_submitted_events').select('*').eq('id', event_id).execute()
        if user_response.data:
            event = user_response.data[0]
            event['user_submitted'] = True
            return event
    except Exception as exc:
        logger.info("public get_event user lookup failed: %s", exc)

    result = pa_db('Events_table').get_event_by_id(event_id)
    if result.get('success') and result.get('data'):
        return result['data']
    return None

def public_get_event_annotated(event_id):
    event = public_get_event(event_id)
    if not event:
        return None
    return attach_show_health([event])[0]

def build_sms_agent():
    return SmsAgent(
        openai_api_key=os.environ.get("OPENAI_API_KEY") or "",
        model=os.environ.get("OPENAI_MODEL", "gpt-4.1"),
        list_events=lambda: public_list_events(columns=SMS_EVENT_COLUMNS),
        get_event=public_get_event,
        add_event=create_user_submitted_event,
        get_user=lambda phone: pa_db("user_table").get_user(phone),
        create_user=lambda phone: pa_db("user_table").create_user(phone, send_welcome=False),
        update_name=lambda phone, name: pa_db("user_table").update_user_name(phone, name),
        update_cities=lambda phone, cities: pa_db("user_table").update_user_cities(phone, cities),
        update_genres=lambda phone, genres: pa_db("user_table").update_user_genres(phone, genres),
        get_favorites=lambda phone: pa_db("favorite_events").get_favorite_events(phone),
        delete_user=lambda phone: pa_db("user_table").delete_user(phone),
        get_conversation=lambda phone: pa_db("sms_conversations").get_sms_conversation(phone),
        save_conversation=lambda phone, messages, started_at, global_rules=None, update_rules=False: pa_db(
            "sms_conversations"
        ).save_sms_conversation(
            phone,
            messages,
            started_at,
            global_rules=global_rules,
            update_rules=update_rules,
        ),
        delete_conversation=lambda phone: pa_db("sms_conversations").delete_sms_conversation(phone),
        list_conversations=lambda: pa_db("sms_conversations").list_sms_conversations(),
        spotify=SpotifyCatalog.from_env(),
        list_venue_places=lambda: pa_db("venue_place_cache")._fetch_all_rows(
            "venue_place_cache", columns=SMS_VENUE_COLUMNS
        ),
        save_venue_place=lambda row: pa_db("venue_place_cache").client.table("venue_place_cache").upsert(row).execute(),
        list_artist_heat=lambda: pa_db("artist_heat_cache")._fetch_all_rows(
            "artist_heat_cache", columns=SMS_HEAT_COLUMNS
        ),
    )

sms_agent = build_sms_agent()

def _warm_sms_caches(force=True):
    try:
        stats = sms_agent.warm_caches(force=force)
        logger.info("SMS caches warmed: %s", stats)
        return stats
    except Exception:
        logger.exception("SMS cache warm failed")
        return None

def twilio_request_is_valid():
    if os.environ.get("TWILIO_VALIDATE_REQUESTS", "false").lower() != "true":
        return True
    token = os.environ.get("TWILIO_AUTH_TOKEN") or pa_db("user_table").auth_token
    signature = request.headers.get("X-Twilio-Signature", "")
    public_url = os.environ.get("PUBLIC_API_URL", "").rstrip("/") + "/sms"
    params = dict(request.form) if request.form else dict(request.args)
    if request.method == "GET" and request.query_string:
        public_url = public_url + "?" + request.query_string.decode()
        params = {}
    return RequestValidator(token).validate(public_url, params, signature)

# Routes
@app.route('/')
def home():
    return "Flask server with scheduled task is running!"

def _send_sms_parts(phone_number, parts):
    """Deliver outbound SMS via Twilio REST (used after fast webhook ACK)."""
    handler = pa_db("user_table")
    client = handler.twilio_client
    from_number = handler.twilio_phone_number
    for part in parts:
        text = (part or "").strip()
        if not text:
            continue
        client.messages.create(body=text, from_=from_number, to=phone_number)


def _sms_reply_worker(phone_number, body):
    """Build reply + send via REST. Safe to run in a child process."""
    try:
        _warm_sms_caches(force=False)
        ack_sent = {"done": False}

        def progress_callback(message):
            # Deep-mode interim SMS so longer lookups can finish without silence.
            if ack_sent["done"]:
                return
            text = (message or "").strip()
            if not text:
                return
            _send_sms_parts(phone_number, [text])
            ack_sent["done"] = True

        reply = sms_agent.reply(
            phone_number,
            body,
            progress_callback=progress_callback,
        ) or "I hit a snag looking that up. Try again in a minute?"
        parts = reply if isinstance(reply, (list, tuple)) else [reply]
        _send_sms_parts(phone_number, parts)
    except Exception:
        logger.exception("async sms reply failed for %s", phone_number)
        try:
            _send_sms_parts(
                phone_number,
                ["I hit a snag looking that up. Try again in a minute?"],
            )
        except Exception:
            logger.exception("async sms fallback send failed for %s", phone_number)


def _spawn_sms_reply(phone_number, body):
    """
    ACK Twilio immediately, then build+send the reply out-of-band.

    Railway/gunicorn (gthread) supports threads — prefer that.
    PythonAnywhere uWSGI has threads disabled, so it uses a detached
    child process via sms_worker.py (SMS_ASYNC_MODE=process).
    """
    mode = (os.environ.get("SMS_ASYNC_MODE") or "thread").strip().lower()
    if mode in {"thread", "threads", "auto"}:
        try:
            threading.Thread(
                target=_sms_reply_worker,
                args=(phone_number, body),
                daemon=True,
                name=f"sms-reply-{(phone_number or '')[-4:]}",
            ).start()
            logger.info(
                "spawned sms thread for %s",
                phone_number[-4:] if phone_number else "",
            )
            return True
        except Exception:
            logger.exception("failed to spawn sms thread; falling back to sync reply")
            return False

    payload = base64.b64encode((body or "").encode("utf-8")).decode("ascii")
    if not os.path.isfile(SMS_WORKER_PATH):
        logger.error("sms_worker.py missing at %s; cannot use process mode", SMS_WORKER_PATH)
        return False
    log_handle = None
    try:
        log_handle = open(SMS_WORKER_LOG, "a", encoding="utf-8")
    except OSError:
        log_handle = subprocess.DEVNULL
    try:
        proc = subprocess.Popen(
            [SMS_PYTHON, SMS_WORKER_PATH, phone_number, payload],
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(SMS_WORKER_PATH) or ".",
            start_new_session=True,
            close_fds=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        logger.info(
            "spawned sms worker pid=%s python=%s for %s",
            proc.pid,
            SMS_PYTHON,
            phone_number[-4:] if phone_number else "",
        )
        return True
    except Exception:
        logger.exception("failed to spawn sms worker; falling back to sync reply")
        return False
    finally:
        if log_handle not in (None, subprocess.DEVNULL):
            try:
                log_handle.close()
            except Exception:
                pass


@app.route('/sms', methods=['GET', 'POST'])
def incoming_sms():
    """Retired show-finder SMS. Favorites 2FA still uses Twilio Verify elsewhere."""
    if request.method == 'GET' and not request.values.get("From") and not request.values.get("Body"):
        return jsonify({
            "status": "retired",
            "message": "SproutMe SMS show-finder is retired. Use the ChatGPT plugin or sproutme-please.com.",
        }), 200
    twiml = MessagingResponse()
    twiml.message(
        "SproutMe SMS is retired. Ask in ChatGPT (SproutMe plugin) or browse sproutme-please.com."
    )
    return Response(str(twiml), mimetype="application/xml")

@app.route('/validate-phone', methods=['POST'])
def validate_phone():
    verification_handler = TwilioVerificationManager()
    data = request.get_json()

    phone_number = data.get("phone_number")
    region = data.get("region", "US")

    if not phone_number:
        return jsonify({"error": "Phone number is required"}), 400

    is_valid = verification_handler.is_valid_phone_number(phone_number, region)
    print(is_valid)  # Debugging

    # Use dictionary key access instead of dot notation
    logging.debug(f"Phone number: {is_valid['formatted_number']}, Region: {region}, Valid: {is_valid['valid']}")

    return jsonify({
        "phone_number": is_valid["formatted_number"],  # Return formatted number
        "region": region,
        "valid": is_valid["valid"]
    })

@app.route('/get_name', methods=['POST'])
def get_name():
    data = request.get_json()
    phone_hash = data.get("phone_hash")
    # Create a DatabaseHandler instance
    db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="user_table"
    )
    
    # Find the phone number from the hash
    phone_number = find_phone_by_hash(db_handler, phone_hash)
    
    if not phone_number:
        return jsonify({"error": "Phone number not found"}), 404
    
    # Retrieve the name associated with the phone number
 
    name = db_handler.get_name_by_phone_number(phone_number)
    
    if not name:
        return jsonify({"error": "Name not found"}), 404
    
    return jsonify({"name": name})

@app.route('/send_2fa', methods=['POST'])
def send_2fa():
    verify_manager = TwilioVerificationManager()
    data = request.get_json()
    phone_number = data.get("phone_number")
    print(phone_number)
    if verify_manager.send_verification(phone_number):
        print("Verification code sent!")
        return jsonify({"phone_number": phone_number}), 200
    
    return jsonify({"error": "Phone number is required"}), 400
    '''   
        # Later, verify the code
        verification_code = input("Enter verification code: ")
        if verify_manager.verify_code(phone_number, verification_code):
            print("Phone number verified successfully!")
        else:
            print("Verification failed.")
    '''
@app.route('/verify_2fa', methods=['POST'])
def verify_2fa():
    verify_manager = TwilioVerificationManager()
    data = request.get_json()

    phone_number = data.get("phone_number")
    verification_code = data.get("verification_code")

    # Validate input data
    if not phone_number or not verification_code:
        return jsonify({"error": "Phone number and verification code are required"}), 400

    # Verify the code
    if verify_manager.verify_code(phone_number, verification_code):
        return jsonify({"phone_number": phone_number,"valid": True}), 200
    else:
        return jsonify({"valid":False}), 400

@app.route('/check_user', methods=['POST'])
def check_user():
    """
    Flask endpoint to check if a user exists with the given phone number and return different statuses.
    """
    # Extract phone_number from query parameters
    data = request.get_json()
    phone_number = data.get("phone_number")
    
    if not phone_number:
        return jsonify({
            "success": False,
            "status": "bad_request",
            "message": "phone_number is required as a query parameter",
            "data": None
        }), 400  # Bad Request
    
    db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="Events_table"
    )
    
    # Call the check_user_name method
    result = db_handler.check_user_name(phone_number)
    
    # Return appropriate status codes
    if result["status"] == "user_with_name":
        return jsonify(result), 200  # OK
    elif result["status"] == "user_without_name":
        return jsonify(result), 206  # Partial Content
    elif result["status"] == "user_not_found":
        return jsonify(result), 404  # Not Found
    else:
        return jsonify(result), 500  # Internal Server Error

@app.route('/update_user_name', methods=['POST'])
def update_user_name():
    data = request.get_json()
    phone_number = data.get("phone_number")
    name = data.get("name")
    db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="user_table"
        )
    
    result = db_handler.update_user_name(phone_number, name)
    print(result,"dsf")
    return jsonify(result)
    

WEB_EVENT_FIELDS = (
    "id",
    "event_name",
    "date",
    "raw_date",
    "venue",
    "city",
    "genre",
    "ticket_info",
    "organizer",
    "event_url",
    "user_submitted",
    "is_favorite",
)
WEB_EVENT_COLUMNS = (
    "id,event_name,headliner,date,raw_date,venue,city,genre,ticket_info,organizer,event_url"
)
WEB_EVENTS_CACHE_TTL = 300
WEB_EVENTS_FILE_CACHE = os.environ.get(
    "WEB_EVENTS_FILE_CACHE",
    str(Path(__file__).resolve().parent / ".cache" / "web_events_catalog.json"),
)
WEB_PAGE_DEFAULT = 50
WEB_PAGE_MAX = 100
_web_events_cache = {"at": 0.0, "events": None}


def _compact_web_event(event):
    if not event:
        return None
    cleaned = sanitize_event(event)
    out = {field: cleaned.get(field) for field in WEB_EVENT_FIELDS if field != "is_favorite"}
    out["user_submitted"] = bool(cleaned.get("user_submitted"))
    out["is_favorite"] = bool(cleaned.get("is_favorite"))
    # Normalize empty genre for frontend consistency
    genre = (out.get("genre") or "").strip()
    out["genre"] = genre if genre else "None"
    # Scores are computed in _load_web_events_catalog; preserve them for cards.
    if cleaned.get("sprout_score") is not None:
        out["sprout_score"] = cleaned.get("sprout_score")
    elif event.get("sprout_score") is not None:
        out["sprout_score"] = event.get("sprout_score")
    parts = cleaned.get("sprout_parts") or event.get("sprout_parts")
    if parts:
        out["sprout_parts"] = parts
    return out


def _parse_event_day(value):
    text_value = str(value or "")
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text_value)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _split_csv_params(*values):
    items = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            parts = value
        else:
            parts = re.split(r"[,|]", str(value))
        for part in parts:
            cleaned = " ".join(str(part).split()).strip()
            if cleaned:
                items.append(cleaned)
    # preserve order, drop dupes case-insensitively
    seen = set()
    out = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _web_city_hit(event, cities):
    if not cities:
        return True
    event_city = " ".join(str(event.get("city") or "").lower().replace(",", " ").split())
    venue = str(event.get("venue") or "").lower()
    paren = re.search(r"\(([^)]+)\)", venue)
    place = " ".join(paren.group(1).lower().replace(",", " ").split()) if paren else ""
    for city in cities:
        needle = " ".join(str(city).lower().replace(",", " ").split())
        if not needle:
            continue
        if event_city and (event_city == needle or needle in event_city or event_city in needle):
            return True
        if place and (place == needle or needle in place or place.startswith(needle)):
            return True
        if re.search(rf"\b{re.escape(needle)}\b", venue):
            return True
    return False


def _web_genre_hit(event, genres):
    if not genres:
        return True
    raw = (event.get("genre") or "").strip()
    parts = [part.strip().lower() for part in re.split(r"[,/;|]+", raw) if part.strip()] if raw else ["none"]
    wanted = [g.strip().lower() for g in genres if g and g.strip()]
    for genre in wanted:
        if genre in parts or any(genre in part or part in genre for part in parts):
            return True
    return False


def _invalidate_web_events_cache():
    _web_events_cache["events"] = None
    _web_events_cache["at"] = 0.0
    try:
        if os.path.exists(WEB_EVENTS_FILE_CACHE):
            os.remove(WEB_EVENTS_FILE_CACHE)
    except OSError:
        pass


def _read_web_events_file_cache(now):
    try:
        st = os.stat(WEB_EVENTS_FILE_CACHE)
        if now - st.st_mtime > WEB_EVENTS_CACHE_TTL:
            return None
        with open(WEB_EVENTS_FILE_CACHE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        events = payload.get("events") if isinstance(payload, dict) else None
        if isinstance(events, list):
            return events
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return None


def _write_web_events_file_cache(events):
    try:
        directory = os.path.dirname(WEB_EVENTS_FILE_CACHE)
        os.makedirs(directory, exist_ok=True)
        tmp_path = WEB_EVENTS_FILE_CACHE + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump({"events": events}, handle, separators=(",", ":"))
        os.replace(tmp_path, WEB_EVENTS_FILE_CACHE)
    except OSError:
        pass


def _load_web_events_catalog(force=False):
    now = time.time()
    if (
        not force
        and _web_events_cache["events"] is not None
        and now - _web_events_cache["at"] < WEB_EVENTS_CACHE_TTL
    ):
        return list(_web_events_cache["events"])

    if not force:
        file_events = _read_web_events_file_cache(now)
        if file_events is not None:
            _web_events_cache["events"] = file_events
            _web_events_cache["at"] = now
            return list(file_events)

    combined = public_list_events(columns=WEB_EVENT_COLUMNS)
    today = datetime.now(timezone.utc).date()
    upcoming = []
    for event in combined:
        compact = _compact_web_event(event)
        if not compact:
            continue
        # Keep headliner for per-page scoring (not exposed as a card field).
        headliner = (event.get("headliner") or "").strip()
        if headliner:
            compact["headliner"] = headliner
        day = _parse_event_day(compact.get("raw_date") or compact.get("date"))
        compact["_sort_day"] = day or date(9999, 12, 31)
        if day is None or day >= today:
            upcoming.append(compact)
    upcoming.sort(key=lambda event: (event["_sort_day"], str(event.get("event_name") or "")))
    for event in upcoming:
        event.pop("_sort_day", None)

    _web_events_cache["events"] = upcoming
    _web_events_cache["at"] = now
    _write_web_events_file_cache(upcoming)
    return list(upcoming)


def _filter_web_events(
    events,
    *,
    cities=None,
    genres=None,
    venues=None,
    organizers=None,
    q="",
    date_start="",
    date_end="",
    favorites_only=False,
):
    matched = []
    query = " ".join(str(q or "").lower().split())
    venue_needles = [v.lower() for v in (venues or [])]
    organizer_needles = [o.lower() for o in (organizers or [])]
    start_day = _parse_event_day(date_start) if date_start else None
    end_day = _parse_event_day(date_end) if date_end else None
    for event in events:
        if favorites_only and not event.get("is_favorite"):
            continue
        if not _web_city_hit(event, cities or []):
            continue
        if not _web_genre_hit(event, genres or []):
            continue
        if venue_needles:
            hay = str(event.get("venue") or "").strip().lower()
            if hay not in venue_needles:
                continue
        if organizer_needles:
            hay = str(event.get("organizer") or "").strip().lower()
            if hay not in organizer_needles:
                continue
        if query:
            blob = " ".join(
                str(event.get(field) or "")
                for field in ("event_name", "headliner", "venue", "city", "genre", "organizer")
            ).lower()
            if query not in blob:
                continue
        day = _parse_event_day(event.get("raw_date") or event.get("date"))
        if start_day and (not day or day < start_day):
            continue
        if end_day and (not day or day > end_day):
            continue
        matched.append(event)
    return matched


def _apply_favorites(events, phone_number):
    if not phone_number:
        return [dict(event) for event in events]
    favorites = pa_db("favorite_events").get_favorite_events(phone_number)
    fav_keys = set()
    for fav in favorites.get("data") or []:
        fav_keys.add((fav.get("event_name"), fav.get("venue"), fav.get("date")))
    out = []
    for event in events:
        item = dict(event)
        item["is_favorite"] = (
            item.get("event_name"),
            item.get("venue"),
            item.get("date"),
        ) in fav_keys
        out.append(item)
    return out


def _price_value(ticket_info):
    text = ticket_info or ""
    if re.search(r"\bfree\b", text, re.I):
        return 0.0
    amounts = [float(match) for match in re.findall(r"\$\s*(\d+(?:\.\d+)?)", text)]
    return min(amounts) if amounts else None


def _sort_web_events(events, price_sort="none"):
    if price_sort in ("asc", "desc"):
        known = []
        unknown = []
        for event in events:
            price = _price_value(event.get("ticket_info"))
            if price is None:
                unknown.append(event)
            else:
                known.append((price, str(event.get("event_name") or ""), event))
        known.sort(key=lambda item: (item[0], item[1]), reverse=(price_sort == "desc"))
        return [item[2] for item in known] + unknown
    return sorted(
        events,
        key=lambda event: (
            _parse_event_day(event.get("raw_date") or event.get("date")) or date(9999, 12, 31),
            str(event.get("event_name") or ""),
        ),
    )


def _build_event_facets(events):
    city_counts = {}
    genre_counts = {}
    venue_counts = {}
    organizer_counts = {}
    for event in events:
        city = (event.get("city") or "").strip() or extract_city(event.get("venue") or "")
        if city:
            city_counts[city] = city_counts.get(city, 0) + 1
        raw_genre = (event.get("genre") or "").strip() or "None"
        for genre in [part.strip() for part in raw_genre.split(",") if part.strip()] or ["None"]:
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
        venue = (event.get("venue") or "").strip()
        if venue:
            venue_counts[venue] = venue_counts.get(venue, 0) + 1
        organizer = (event.get("organizer") or "").strip()
        if organizer:
            organizer_counts[organizer] = organizer_counts.get(organizer, 0) + 1

    def as_list(counts):
        return [
            {"name": name, "count": count}
            for name, count in sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))
        ]

    return {
        "cities": as_list(city_counts),
        "genres": as_list(genre_counts),
        "venues": as_list(venue_counts),
        "organizers": as_list(organizer_counts),
    }


def _parse_web_event_query(args):
    cities = _split_csv_params(args.getlist("city") or args.getlist("cities") or args.get("city") or args.get("cities"))
    genres = _split_csv_params(args.getlist("genre") or args.getlist("genres") or args.get("genre") or args.get("genres"))
    venues = _split_csv_params(args.getlist("venue") or args.getlist("venues") or args.get("venue") or args.get("venues"))
    organizers = _split_csv_params(
        args.getlist("organizer") or args.getlist("organizers") or args.get("organizer") or args.get("organizers")
    )
    try:
        limit = min(max(int(args.get("limit", WEB_PAGE_DEFAULT)), 1), WEB_PAGE_MAX)
    except (TypeError, ValueError):
        limit = WEB_PAGE_DEFAULT
    try:
        offset = max(int(args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        offset = 0
    favorites_only = str(args.get("favorites_only") or args.get("starred") or "").lower() in {
        "1", "true", "yes", "on",
    }
    price_sort = (args.get("price_sort") or args.get("sort") or "none").strip().lower()
    if price_sort not in ("asc", "desc", "none"):
        price_sort = "none"
    return {
        "cities": cities,
        "genres": genres,
        "venues": venues,
        "organizers": organizers,
        "q": (args.get("q") or args.get("search") or "").strip(),
        "date_start": (args.get("date_start") or args.get("start") or "").strip(),
        "date_end": (args.get("date_end") or args.get("end") or "").strip(),
        "limit": limit,
        "offset": offset,
        "favorites_only": favorites_only,
        "price_sort": price_sort,
        "phone_number": (args.get("phone_number") or "").strip() or None,
    }

@app.route('/events', methods=['GET'])
def get_events_for_user():
    try:
        params = _parse_web_event_query(request.args)
        catalog = _load_web_events_catalog()
        events = _apply_favorites(catalog, params["phone_number"])
        matched = _filter_web_events(
            events,
            cities=params["cities"],
            genres=params["genres"],
            venues=params["venues"],
            organizers=params["organizers"],
            q=params["q"],
            date_start=params["date_start"],
            date_end=params["date_end"],
            favorites_only=params["favorites_only"],
        )
        matched = _sort_web_events(matched, params["price_sort"])
        total = len(matched)
        limit = params["limit"]
        offset = params["offset"]
        page = matched[offset:offset + limit]
        # Score only the returned page so cold catalog loads stay fast.
        page = attach_show_health(page)
        for event in page:
            event.pop("headliner", None)
        return jsonify({
            "success": True,
            "message": "Events retrieved",
            "data": page,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }), 200
    except Exception as e:
        logger.exception("get_events_for_user failed")
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}",
            "data": None
        }), 500


@app.route('/events/facets', methods=['GET'])
def get_event_facets():
    try:
        params = _parse_web_event_query(request.args)
        exclude = (request.args.get("exclude") or "").strip().lower()
        catalog = _load_web_events_catalog()
        events = _apply_favorites(catalog, params["phone_number"])
        matched = _filter_web_events(
            events,
            cities=[] if exclude == "cities" else params["cities"],
            genres=[] if exclude == "genres" else params["genres"],
            venues=[] if exclude == "venues" else params["venues"],
            organizers=[] if exclude == "organizers" else params["organizers"],
            q="" if exclude == "search" else params["q"],
            date_start="" if exclude == "date" else params["date_start"],
            date_end="" if exclude == "date" else params["date_end"],
            favorites_only=False if exclude == "starred" else params["favorites_only"],
        )
        facets = _build_event_facets(matched)
        return jsonify({
            "success": True,
            "message": "Event facets retrieved",
            "data": facets,
            "total": len(matched),
        }), 200
    except Exception as e:
        logger.exception("get_event_facets failed")
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}",
            "data": None
        }), 500



@app.route('/add_event', methods=['POST'])
def add_event():
    try:
        result, status = create_user_submitted_event(request.get_json() or {})
        if status < 400:
            _invalidate_web_events_cache()
        return jsonify(result), status
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}",
            "data": None
        }), 500

@app.route('/star_event', methods=['POST'])
def star_event():
    """
    Add an event to a user's favorites.
    """
    try:
        data = request.get_json()
        
        # Extract data from request
        phone_number = data.get('phone_number')
        print(data,"hi")
        event = data.get('event')
        event_metadata = data.get('event_metadata')
        
        # Validate required data
        if not phone_number:
            return jsonify({
                "success": False,
                "message": "Phone number is required and cannot be null. Check your frontend code to ensure you're sending actualPhoneNumber correctly.",
                "data": None
            }), 400
            
        if not event and not event_metadata:
            return jsonify({
                "success": False,
                "message": "Event data or event metadata is required",
                "data": None
            }), 400
        
        # Use event_metadata if event is not available
        if not event and event_metadata:
            event = event_metadata
            
        # Copy fields from event_metadata to event if they exist in metadata but not in event
        if event_metadata:
            for field in ['raw_date', 'ticket_info', 'genre', 'event_url']:
                if event_metadata.get(field) and not event.get(field):
                    event[field] = event_metadata.get(field)
        
        # Initialize the database handler
        db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="favorite_events"
        )
        
        # Call the star_event method
        result = db_handler.star_event(phone_number, event)
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}",
            "data": None
        }), 500

@app.route('/unstar_event', methods=['POST'])
def unstar_event():
    """
    Remove an event from a user's favorites.
    """
    try:
        data = request.get_json()
        
        # Extract data from request
        phone_number = data.get('phone_number')
        event_metadata = data.get('event_metadata')
        
        # Validate required data
        if not phone_number:
            return jsonify({
                "success": False,
                "message": "Phone number is required",
                "data": None
            }), 400
            
        if not event_metadata:
            return jsonify({
                "success": False,
                "message": "Event metadata is required",
                "data": None
            }), 400
            
        # Provide default values for missing fields
        if not event_metadata.get('raw_date') and event_metadata.get('date'):
            event_metadata['raw_date'] = event_metadata.get('date')
            
        # Make sure ticket_info, genre, and event_url exist with at least empty strings
        for field in ['ticket_info', 'genre', 'event_url']:
            if field not in event_metadata:
                event_metadata[field] = ""
        
        # Initialize the database handler
        db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="favorite_events"
        )
        
        # Call the unstar_event method
        result = db_handler.unstar_event(phone_number, event_metadata)
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}",
            "data": None
        }), 500

@app.route('/favorite_events', methods=['GET'])
def get_favorite_events():
    """
    Get all favorite events for a user.
    """
    try:
        # Extract query parameters
        phone_number = request.args.get('phone_number')
        
        # Validate required data
        if not phone_number:
            return jsonify({
                "success": False,
                "message": "Phone number is required",
                "data": None
            }), 400
        
        # Initialize the database handler
        db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="favorite_events"
        )
        
        # Call the get_favorite_events method
        result = with_show_health(db_handler.get_favorite_events(phone_number))
        
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}",
            "data": None
        }), 500

@app.route('/user', methods=['POST'])
def create_new_user():
    """
    Endpoint to create a new user with an empty genre_list and city_list
    """
    data = request.get_json()
    phone_number = data.get("phone_number")
    
    if not phone_number:
        return jsonify({"error": "Phone number is required"}), 400
    
    # Initialize DatabaseHandler
    db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="user_table"
    )
    
    result = db_handler.create_user(phone_number)
    
    if result["success"]:
        return jsonify(result), 201
    else:
        return jsonify(result), 400

@app.route('/user', methods=['GET'])
def get_user():
    """
    Endpoint to retrieve a user based on the provided phone number.
    """
    phone_number = request.args.get("phone_number")  # Get from query params

    if not phone_number:
        return jsonify({"error": "Phone number is required"}), 400

    # Initialize DatabaseHandler
    db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="user_table"
    )

    result = db_handler.get_user(phone_number)

    if result["success"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 404










@app.route('/status')
def status():
    """
    Status endpoint to check if the service is running.
    """
    return jsonify({
        "status": "running",
        "sms_agent": "retired",
        "message": "Service is running. SMS show-finder is retired; ChatGPT MCP/API is the agent surface.",
    })


@app.route("/cron/sms-compact", methods=["POST", "GET"])
def cron_sms_compact():
    """Retired with the SMS show-finder product."""
    return jsonify({
        "success": False,
        "message": "SMS compact cron is retired.",
    }), 410


# Manual trigger endpoint no longer needed as we're not sending SMS notifications
@app.route('/run-task', methods=['POST'])
def run_task_manually():
    """
    This endpoint is deprecated as we're removing SMS interactions.
    """
    return jsonify({
        "success": False,
        "message": "SMS notifications have been disabled",
    }), 400

@app.route('/favorite_events_by_hash', methods=['GET'])
def get_favorite_events_by_hash():
    """
    Get all favorite events for a user identified by their phone hash.
    Also returns all events with favorite status marked.
    """

    try:
        # Extract query parameters
        phone_hash = request.args.get('phone_hash')
        print(phone_hash,"phone_hash")
        include_all_events = request.args.get('include_all', 'false').lower() == 'true'
        
        # Validate required data
        if not phone_hash:
            return jsonify({
                "success": False,
                "message": "Phone hash is required",
                "data": None
            }), 400
        
        # Initialize the database handler
        db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="favorite_events"
        )
        
        # Find the phone number from the hash
        phone_number = find_phone_by_hash(db_handler, phone_hash)
        
        if not phone_number:
            return jsonify({
                "success": False,
                "message": "No user found with this hash",
                "data": None
            }), 404
        
        # If include_all_events is true, return all events with favorite status
        if include_all_events:
            events_db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="Events_table"
            )
            result = events_db_handler.get_events_with_favorite_status(phone_number)
        else:
            # Just get the favorite events
            result = db_handler.get_favorite_events(phone_number)
        
        result = with_show_health(result)
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}",
            "data": None
        }), 500

@app.route('/favorite_events_by_phone', methods=['GET'])
def get_favorite_events_by_phone():
    """
    Get all favorite events for a user identified by their phone number.
    Also returns all events with favorite status marked.
    
    Query Parameters:
    - phone_number: User's phone number
    - include_all: 'true' to include all events with favorite status
    - raw_date: Optional parameter to filter events by raw_date
    """
    try:
        # Extract query parameters
        phone_number = request.args.get('phone_number')
        raw_date = request.args.get('raw_date')
        print(phone_number, "phone_number")
        include_all_events = request.args.get('include_all', 'false').lower() == 'true'
        
        # Validate required data
        if not phone_number:
            return jsonify({
                "success": False,
                "message": "Phone number is required",
                "data": None
            }), 400
        
        # If include_all_events is true, return all events with favorite status
        if include_all_events:
            events_db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="Events_table"
            )
            result = events_db_handler.get_events_with_favorite_status(phone_number)
        else:
            # Initialize the database handler for favorite events
            db_handler = DatabaseHandler(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        table_name="favorite_events"
            )
            # Just get the favorite events
            result = db_handler.get_favorite_events(phone_number)
        
        # Filter results by raw_date if provided
        if raw_date and result.get('data'):
            filtered_data = [event for event in result['data'] if event.get('raw_date') == raw_date]
            result['data'] = filtered_data
            result['message'] = f"Events filtered by raw_date: {raw_date}"
            
        result = with_show_health(result)
        return jsonify(result), 200 if result['success'] else 400
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}",
            "data": None
        }), 500

def mcp_start_sms_login(phone):
    verify_manager = TwilioVerificationManager()
    check = verify_manager.is_valid_phone_number(phone or "", region="US")
    if not check.get("valid"):
        return {"success": False, "message": "Invalid phone number. Use E.164 like +12065551212."}
    formatted = check.get("formatted_number") or phone
    if not verify_manager.send_verification(formatted):
        return {"success": False, "message": "Could not send verification SMS. Try again shortly."}
    return {
        "success": True,
        "phone": formatted,
        "message": "SMS code sent. Ask the user for the code, then call verify_sms_login.",
    }


def mcp_verify_sms_login(phone, code):
    verify_manager = TwilioVerificationManager()
    check = verify_manager.is_valid_phone_number(phone or "", region="US")
    if not check.get("valid"):
        return {"success": False, "message": "Invalid phone number."}
    formatted = check.get("formatted_number") or phone
    if not (code or "").strip():
        return {"success": False, "message": "Verification code is required."}
    if not verify_manager.verify_code(formatted, str(code).strip()):
        return {"success": False, "message": "Invalid or expired code."}
    pa_db("user_table").create_user(formatted, send_welcome=False)
    session = issue_session(formatted)
    return {
        "success": True,
        "session_token": session["session_token"],
        "expires_in": session.get("expires_in"),
        "expires_at": session.get("expires_at"),
        "phone": formatted,
        "message": (
            "Logged in. session_token does not expire — reuse it for this whole chat "
            "(list_favorites, set_favorite, search with is_favorite). "
            "A new chat needs login again if they want favorites/taste."
        ),
    }


def mcp_list_favorites(phone):
    return pa_db("favorite_events").get_favorite_events(phone)


def mcp_set_favorite(phone, event_id, starred):
    event = public_get_event_annotated(event_id)
    if not event:
        return {"success": False, "message": f"No event found with id {event_id}"}
    db = pa_db("favorite_events")
    if starred:
        result = db.star_event(phone, event)
    else:
        result = db.unstar_event(phone, event)
    if result.get("success"):
        result["event_id"] = event_id
        result["starred"] = bool(starred)
        result["event"] = {
            "id": event.get("id"),
            "event_name": event.get("event_name"),
            "venue": event.get("venue"),
            "date": event.get("date"),
        }
    return result


register_public_api(
    app,
    list_events=public_list_events_annotated,
    get_event=public_get_event_annotated,
    add_event=create_user_submitted_event,
    public_base_url=os.environ.get("PUBLIC_API_URL", "").rstrip("/") or "http://localhost:5050",
    api_key=os.environ.get("AGENT_API_KEY", ""),
    start_sms_login=mcp_start_sms_login,
    verify_sms_login=mcp_verify_sms_login,
    list_favorites=mcp_list_favorites,
    set_favorite=mcp_set_favorite,
)

register_sitemaps(
    app,
    load_catalog=_load_web_events_catalog,
    build_facets=_build_event_facets,
    extract_city=extract_city,
    parse_event_day=_parse_event_day,
)

if __name__ == "__main__":
    logger.info("Starting Flask server")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5050")), debug=False)
