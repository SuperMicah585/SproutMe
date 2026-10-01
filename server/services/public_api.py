import json
import re
import time
import uuid
from datetime import date, timedelta
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from flask import Response, jsonify, request

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL = "2025-03-26"
MAX_RESULTS = 20
DEFAULT_LIMIT = 8
CACHE_TTL_SECONDS = 60
# Lean fields for LLM consumers — ChatGPT narrates; no SMS card strings.
PUBLIC_EVENT_FIELDS = (
    "id",
    "event_name",
    "date",
    "raw_date",
    "venue",
    "city",
    "genre",
    "ticket_info",
    "event_url",
    "headliner",
)

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

CHATGPT_GPT_INSTRUCTIONS = """You are SproutMe, an electronic-music show finder for North America.

Catalog tools return structured evidence JSON. You narrate — never invent.

Rules:
- Only recommend events in tool results (`data`). If `data` is empty, mention `later` when present, otherwise say `miss_reason` honestly.
- Never invent shows, venues, prices, dates, lineups, or ticket links.
- Prefer city + genre + date filters over vague free-text.
- Date may be YYYY-MM-DD or: tonight, tomorrow, saturday, this weekend, next weekend, in 2 days.
- Artist asks → findArtistShows / find_artist_shows first.
- Genre/city nights → searchEvents / search_events.
- Keep answers short: lead with 1–2 best options, then offer to refine.
- Do not call addEvent / add_event unless the user explicitly wants to submit a show (requires API key).
"""

_events_cache = {"at": 0.0, "events": None}

AFFILIATE_QUERY_KEYS = {
    "aff", "affiliate", "afflky", "aref", "afsrc", "camefrom",
    "clickid", "dice_source", "eventref", "fbclid", "gclid",
    "irgwc", "mc_cid", "mc_eid", "nts_trk", "pc", "promo",
    "ref", "referral_id",
}


def clean_event_url(url):
    if not url or not isinstance(url, str):
        return url or ""
    parsed = urlparse(url.strip())
    if not parsed.query:
        return url.strip()
    kept = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = (key or "").lower()
        val = (value or "").lower()
        if lowered == "t" and val == "19hz":
            continue
        if lowered in AFFILIATE_QUERY_KEYS or lowered.startswith("utm_") or lowered.startswith("utm-"):
            continue
        if lowered == "cid" and val.startswith("aff"):
            continue
        kept.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(kept, doseq=True)))


def sanitize_event(event):
    if not event:
        return event
    cleaned = dict(event)
    for field in ("event_url", "event_link_url"):
        if cleaned.get(field):
            cleaned[field] = clean_event_url(cleaned[field])
    return cleaned


def compact_event(event):
    if not event:
        return None
    event = sanitize_event(event)
    compact = {field: event.get(field) for field in PUBLIC_EVENT_FIELDS}
    if not compact.get("headliner"):
        compact.pop("headliner", None)
    # Drop empty optional fields so the LLM isn't flooded with nulls.
    for key in ("ticket_info", "genre", "city", "event_url"):
        if not compact.get(key):
            compact.pop(key, None)
    return compact


def _haystack(event):
    parts = [
        event.get("event_name"),
        event.get("headliner"),
        event.get("venue"),
        event.get("city"),
        event.get("genre"),
        event.get("organizer"),
        event.get("date"),
        event.get("raw_date"),
        event.get("ticket_info"),
    ]
    return " ".join(str(part) for part in parts if part).lower()


def _today():
    return date.today()


def _parse_day(text):
    text = (text or "").strip()
    if not text:
        return None
    match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


def _next_weekday(weekday, today=None):
    today = today or _today()
    return today + timedelta(days=(weekday - today.weekday()) % 7)


def parse_date_window(value, today=None):
    """Parse YYYY-MM-DD or phrases like saturday / this weekend / in 2 days."""
    if value is None or value == "":
        return None, None
    if isinstance(value, date):
        return value, value
    text = str(value).strip()
    if not text:
        return None, None
    today = today or _today()
    weekday = today.weekday()
    friday = today - timedelta(days=weekday - 4) if weekday >= 4 else today + timedelta(days=4 - weekday)
    sunday = friday + timedelta(days=2)
    lowered = text.lower()
    if re.search(r"\b(tonight|today|this evening)\b", lowered):
        return today, today
    if re.search(r"\btomorrow\b", lowered):
        day = today + timedelta(days=1)
        return day, day
    in_days = re.search(r"\bin\s+(\d+)\s+days?\b", lowered)
    if in_days:
        day = today + timedelta(days=int(in_days.group(1)))
        return day, day
    if re.search(r"\bthis weekend\b", lowered):
        start = max(today, friday)
        end = sunday
        if start > end:
            start = friday + timedelta(days=7)
            end = sunday + timedelta(days=7)
        return start, end
    if re.search(r"\bnext weekend\b", lowered):
        return friday + timedelta(days=7), sunday + timedelta(days=7)
    if re.search(r"\bthis week\b", lowered):
        end = today + timedelta(days=(6 - today.weekday()))
        return today, end
    if re.search(r"\bnext week\b", lowered):
        start = today + timedelta(days=1)
        days_until_sunday = (6 - today.weekday()) % 7
        end = today + timedelta(days=days_until_sunday + 7)
        if start > end:
            end = start + timedelta(days=6)
        return start, end
    wants_next = bool(re.search(r"\bnext\b", lowered))
    for name, index in WEEKDAYS.items():
        if re.search(rf"\b{name}s?\b", lowered):
            day = _next_weekday(index, today)
            if wants_next and day == today:
                day += timedelta(days=7)
            return day, day
    parsed = _parse_day(text)
    if parsed:
        return parsed, parsed
    # Legacy exact substring fallback signal
    return None, None


def event_day(event):
    raw = (event.get("raw_date") or "").strip()
    parsed = _parse_day(raw)
    if parsed:
        return parsed
    return _parse_day(event.get("date") or "")


def _name_mentions_artist(event_name, query):
    name = event_name or ""
    needle = re.sub(r"\s+", " ", (query or "").strip())
    if len(needle) < 2 or not name:
        return False
    if re.search(rf"\b{re.escape(needle)}\b", name, re.I):
        return True
    compact_name = re.sub(r"[^a-z0-9]+", "", name.lower())
    compact_needle = re.sub(r"[^a-z0-9]+", "", needle.lower())
    if len(compact_needle) >= 5 and compact_needle in compact_name:
        return True
    words = [word for word in re.split(r"\W+", name.lower()) if len(word) >= 4]
    return any(
        abs(len(compact_needle) - len(word)) <= 2
        and SequenceMatcher(None, compact_needle, word).ratio() >= 0.86
        for word in words
    )


def filter_events(events, q=None, city=None, genre=None, date=None, limit=DEFAULT_LIMIT, offset=0):
    q = (q or "").strip().lower()
    city = (city or "").strip().lower()
    genre = (genre or "").strip().lower()
    date_raw = (date or "").strip()
    date_l = date_raw.lower().replace("-", "/")
    start, end = parse_date_window(date_raw)
    today = _today()
    try:
        limit = min(max(int(limit), 1), MAX_RESULTS)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    try:
        offset = max(int(offset), 0)
    except (TypeError, ValueError):
        offset = 0

    matched = []
    later = []
    for event in events:
        day = event_day(event)
        if day and day < today:
            continue
        blob = _haystack(event)
        if q and q not in blob:
            continue
        if city and city not in (event.get("city") or "").lower() and city not in (event.get("venue") or "").lower():
            continue
        if genre and genre not in (event.get("genre") or "").lower():
            continue
        if start and end:
            if day and start <= day <= end:
                matched.append(compact_event(event))
            elif day and day > end:
                later.append(compact_event(event))
            continue
        if date_l:
            raw = (event.get("raw_date") or "").lower().replace("-", "/")
            display = (event.get("date") or "").lower()
            if date_l not in raw and date_l not in display:
                continue
        matched.append(compact_event(event))

    applied = {
        "q": q or None,
        "city": city or None,
        "genre": genre or None,
        "date": date_raw or None,
        "date_start": start.isoformat() if start else None,
        "date_end": end.isoformat() if end else None,
    }
    page = matched[offset:offset + limit]
    later_page = later[: min(3, limit)] if not page and later else (later[:1] if page else [])
    miss_reason = None
    if not page and not later_page:
        bits = ["No catalog matches"]
        if genre:
            bits.append(f"for {genre}")
        if city:
            bits.append(f"in {city}")
        if date_raw:
            bits.append(f"on {date_raw}")
        miss_reason = " ".join(bits) + "."
    return {
        "total": len(matched),
        "limit": limit,
        "offset": offset,
        "data": page,
        "later": later_page,
        "applied": applied,
        "miss_reason": miss_reason,
    }


def find_artist_shows(events, artist, city=None, date=None, limit=5):
    artist = re.sub(r"\s+", " ", (artist or "").strip())
    if len(artist) < 2:
        return {
            "total": 0,
            "limit": limit,
            "offset": 0,
            "data": [],
            "later": [],
            "applied": {"artist": artist or None, "city": city, "date": date},
            "miss_reason": "Provide an artist name.",
        }
    city_l = (city or "").strip().lower()
    start, end = parse_date_window(date)
    today = _today()
    try:
        limit = min(max(int(limit), 1), MAX_RESULTS)
    except (TypeError, ValueError):
        limit = 5

    hits = []
    for event in events or []:
        day = event_day(event)
        if day and day < today:
            continue
        if not (
            _name_mentions_artist(event.get("headliner"), artist)
            or _name_mentions_artist(event.get("event_name"), artist)
        ):
            continue
        if city_l and city_l not in (event.get("city") or "").lower() and city_l not in (event.get("venue") or "").lower():
            continue
        hits.append(event)

    hits.sort(key=lambda event: (
        0 if (event.get("event_name") or "").strip().lower() == artist.lower() else 1,
        event_day(event) or date.max,
    ))

    in_window = []
    later = []
    for event in hits:
        day = event_day(event)
        if start and end:
            if day and start <= day <= end:
                in_window.append(compact_event(event))
            elif day:
                later.append(compact_event(event))
        else:
            in_window.append(compact_event(event))

    data = in_window[:limit]
    later_out = later[:limit] if not data else later[:1]
    applied = {
        "artist": artist,
        "city": city or None,
        "date": date or None,
        "date_start": start.isoformat() if start else None,
        "date_end": end.isoformat() if end else None,
    }
    miss_reason = None
    if not data and not later_out:
        where = f" in {city}" if city else ""
        when = f" for {date}" if date else ""
        miss_reason = f"No cataloged {artist} show{where}{when}."
    return {
        "total": len(in_window),
        "limit": limit,
        "offset": 0,
        "data": data,
        "later": later_out,
        "applied": applied,
        "miss_reason": miss_reason,
    }


def build_openapi(public_base_url):
    date_desc = (
        "YYYY-MM-DD or a relative phrase: tonight, tomorrow, saturday, "
        "this weekend, next weekend, in 2 days"
    )
    event_list_response = {
        "description": (
            "Matching events. Always read `data` first; if empty use `later` or "
            "surface `miss_reason`. Never invent shows."
        )
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "SproutMe Public Events API",
            "version": "1.2.0",
            "description": (
                "EDM show catalog for ChatGPT plugins / MCP. "
                "Tools return compact evidence JSON (data, later, applied, miss_reason); "
                "the LLM narrates — never invent events. "
                f"Instructions: {public_base_url}/chatgpt/instructions. "
                "Auth: none for search/find/get; Bearer AGENT_API_KEY for addEvent."
            ),
        },
        "servers": [{"url": public_base_url, "description": "SproutMe API"}],
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "AGENT_API_KEY — required only for addEvent writes",
                }
            }
        },
        "paths": {
            "/v1/events": {
                "get": {
                    "operationId": "searchEvents",
                    "summary": "Search upcoming EDM events by city/genre/date",
                    "description": (
                        "Use for genre/city/date night asks like 'house Saturday Seattle'. "
                        "Returns evidence pack: data, later, applied, miss_reason."
                    ),
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string"}, "description": "Free-text across name, venue, city, genre, organizer"},
                        {"name": "city", "in": "query", "schema": {"type": "string"}},
                        {"name": "genre", "in": "query", "schema": {"type": "string"}, "description": "e.g. house, techno, drum and bass"},
                        {"name": "date", "in": "query", "schema": {"type": "string"}, "description": date_desc},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": DEFAULT_LIMIT, "maximum": MAX_RESULTS}},
                        {"name": "offset", "in": "query", "schema": {"type": "integer", "default": 0}},
                    ],
                    "responses": {"200": event_list_response},
                },
                "post": {
                    "operationId": "addEvent",
                    "summary": "Submit a user event that survives the daily scrape",
                    "security": [{"bearerAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["event_name", "venue", "date"],
                                    "properties": {
                                        "event_name": {"type": "string"},
                                        "venue": {"type": "string", "description": "Include city in parentheses when possible, e.g. Neumos (Seattle)"},
                                        "date": {"type": "string", "description": "Display date or YYYY-MM-DD"},
                                        "raw_date": {"type": "string"},
                                        "genre": {"type": "string"},
                                        "ticket_info": {"type": "string"},
                                        "organizer": {"type": "string"},
                                        "event_url": {"type": "string"},
                                        "city": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "201": {"description": "Event created"},
                        "400": {"description": "Missing required fields"},
                        "401": {"description": "Missing or invalid API key"},
                    },
                },
            },
            "/v1/artists/shows": {
                "get": {
                    "operationId": "findArtistShows",
                    "summary": "Find catalog shows for a named artist",
                    "description": (
                        "Mandatory artist name probe across event_name/headliner. "
                        "Use for 'Bassvictim Seattle' / 'is X playing'."
                    ),
                    "parameters": [
                        {"name": "artist", "in": "query", "required": True, "schema": {"type": "string"}},
                        {"name": "city", "in": "query", "schema": {"type": "string"}},
                        {"name": "date", "in": "query", "schema": {"type": "string"}, "description": date_desc},
                        {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 5, "maximum": MAX_RESULTS}},
                    ],
                    "responses": {"200": event_list_response},
                }
            },
            "/v1/events/{event_id}": {
                "get": {
                    "operationId": "getEvent",
                    "summary": "Get one event by numeric id",
                    "parameters": [
                        {"name": "event_id", "in": "path", "required": True, "schema": {"type": "integer"}},
                    ],
                    "responses": {
                        "200": {"description": "Event"},
                        "404": {"description": "Not found"},
                    },
                }
            },
            "/chatgpt/instructions": {
                "get": {
                    "operationId": "getChatGptInstructions",
                    "summary": "Paste-ready Custom GPT system instructions",
                    "responses": {"200": {"description": "Plain text instructions"}},
                }
            },
        },
    }


def build_llms_txt(public_base_url):
    return f"""# SproutMe

SproutMe lists electronic music (EDM) shows across North America.

## Primary surface: ChatGPT plugin / MCP

Catalog is source of truth. Tools return compact evidence JSON; ChatGPT narrates.
Do not scrape the website. Never invent shows.

- MCP: POST {public_base_url}/mcp
- OpenAPI: {public_base_url}/openapi.json
- Agent instructions: {public_base_url}/chatgpt/instructions
- Search: GET {public_base_url}/v1/events?city=Seattle&genre=house&date=saturday&limit=8
- Find artist: GET {public_base_url}/v1/artists/shows?artist=Bassvictim&city=Seattle
- Get one event: GET {public_base_url}/v1/events/{{id}}
- Add event (Bearer AGENT_API_KEY): POST {public_base_url}/v1/events

MCP tools (reads): search_events, find_artist_shows, get_event.
add_event is write-gated and omitted from the default plugin tool list.

Evidence pack fields: data, later, applied, miss_reason.
Each event: id, event_name, date, raw_date, venue, city, genre, ticket_info, event_url, headliner.

Website: https://sproutme-please.com (browse only; SMS show-finder is retired).
"""


MCP_TOOLS = [
    {
        "name": "search_events",
        "description": (
            "Search upcoming EDM / electronic music events in North America. "
            "Pass city, genre, and/or date (YYYY-MM-DD or saturday/this weekend/tonight). "
            "Returns compact evidence: data[], later[], applied, miss_reason. "
            "Narrate from data only; if empty use later or miss_reason — never invent."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Free-text search (artist, venue, city, genre)"},
                "city": {"type": "string"},
                "genre": {"type": "string", "description": "e.g. house, techno, drum and bass"},
                "date": {"type": "string", "description": "YYYY-MM-DD or tonight/saturday/this weekend"},
                "limit": {"type": "integer", "default": DEFAULT_LIMIT, "maximum": MAX_RESULTS},
            },
        },
    },
    {
        "name": "find_artist_shows",
        "description": (
            "Find catalog shows for a named artist (name match on event_name/headliner). "
            "Returns evidence pack — narrate from data; empty + miss_reason means not cataloged."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["artist"],
            "properties": {
                "artist": {"type": "string"},
                "city": {"type": "string"},
                "date": {"type": "string"},
                "limit": {"type": "integer", "default": 5, "maximum": MAX_RESULTS},
            },
        },
    },
    {
        "name": "get_event",
        "description": "Get one SproutMe event by numeric id from search_events / find_artist_shows.",
        "inputSchema": {
            "type": "object",
            "required": ["event_id"],
            "properties": {
                "event_id": {"type": "integer"},
            },
        },
    },
]

# Write tool — listed only when Bearer is present; still callable with auth.
MCP_WRITE_TOOLS = [
    {
        "name": "add_event",
        "description": (
            "Submit a new event to the SproutMe catalog (requires Bearer AGENT_API_KEY). "
            "Only when the user explicitly wants to publish a show."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["event_name", "venue", "date"],
            "properties": {
                "event_name": {"type": "string"},
                "venue": {"type": "string"},
                "date": {"type": "string"},
                "raw_date": {"type": "string"},
                "genre": {"type": "string"},
                "ticket_info": {"type": "string"},
                "organizer": {"type": "string"},
                "event_url": {"type": "string"},
                "city": {"type": "string"},
            },
        },
    },
]


def _wants_sse():
    accept = (request.headers.get("Accept") or "").lower()
    if "application/json" in accept:
        return False
    return "text/event-stream" in accept


def _jsonrpc_result(msg_id, result):
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _jsonrpc_error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _mcp_response(payload, session_id, status=200):
    headers = {
        "Mcp-Session-Id": session_id,
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, Mcp-Session-Id, MCP-Protocol-Version",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    }
    if payload is None:
        return Response(status=202, headers=headers)
    if _wants_sse():
        body = f"event: message\ndata: {json.dumps(payload)}\n\n"
        headers["Content-Type"] = "text/event-stream"
        headers["Cache-Control"] = "no-cache"
        return Response(body, status=status, headers=headers)
    headers["Content-Type"] = "application/json"
    return Response(json.dumps(payload), status=status, headers=headers)


def register_public_api(app, list_events, get_event, add_event, public_base_url, api_key=""):
    """
    list_events() -> list[dict]
    get_event(event_id) -> dict | None
    add_event(payload_dict) -> (result_dict, status_code)
    """

    def cached_events():
        now = time.time()
        if _events_cache["events"] is not None and now - _events_cache["at"] < CACHE_TTL_SECONDS:
            return _events_cache["events"]
        events = list_events() or []
        _events_cache["events"] = events
        _events_cache["at"] = now
        return events

    def invalidate_cache():
        _events_cache["events"] = None
        _events_cache["at"] = 0.0

    def authorized_for_write():
        if not api_key:
            return True
        header = request.headers.get("Authorization") or ""
        token = header[7:].strip() if header.lower().startswith("bearer ") else header
        return token == api_key

    @app.route("/openapi.json", methods=["GET"])
    def openapi_spec():
        response = jsonify(build_openapi(public_base_url))
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    @app.route("/llms.txt", methods=["GET"])
    def llms_txt():
        response = Response(build_llms_txt(public_base_url), mimetype="text/plain")
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    @app.route("/chatgpt/instructions", methods=["GET", "OPTIONS"])
    def chatgpt_instructions():
        if request.method == "OPTIONS":
            return _cors_preflight()
        response = Response(CHATGPT_GPT_INSTRUCTIONS, mimetype="text/plain; charset=utf-8")
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    @app.route("/v1/events", methods=["GET", "OPTIONS"])
    def v1_search_events():
        if request.method == "OPTIONS":
            return _cors_preflight()
        result = filter_events(
            cached_events(),
            q=request.args.get("q"),
            city=request.args.get("city"),
            genre=request.args.get("genre"),
            date=request.args.get("date"),
            limit=request.args.get("limit", DEFAULT_LIMIT),
            offset=request.args.get("offset", 0),
        )
        response = jsonify({
            "success": True,
            "message": "Events retrieved" if result.get("data") or result.get("later") else (result.get("miss_reason") or "No matches"),
            **result,
        })
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    @app.route("/v1/artists/shows", methods=["GET", "OPTIONS"])
    def v1_find_artist_shows():
        if request.method == "OPTIONS":
            return _cors_preflight()
        result = find_artist_shows(
            cached_events(),
            artist=request.args.get("artist") or request.args.get("q") or "",
            city=request.args.get("city"),
            date=request.args.get("date"),
            limit=request.args.get("limit", 5),
        )
        response = jsonify({
            "success": bool(result.get("data") or result.get("later")),
            "message": (
                "Artist shows retrieved"
                if result.get("data") or result.get("later")
                else (result.get("miss_reason") or "No matches")
            ),
            **result,
        })
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    @app.route("/v1/events/<int:event_id>", methods=["GET", "OPTIONS"])
    def v1_get_event(event_id):
        if request.method == "OPTIONS":
            return _cors_preflight()
        event = compact_event(get_event(event_id))
        if not event:
            response = jsonify({"success": False, "message": f"No event found with id {event_id}", "data": None})
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response, 404
        response = jsonify({"success": True, "data": event})
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    @app.route("/v1/events", methods=["POST"])
    def v1_add_event():
        if not authorized_for_write():
            response = jsonify({"success": False, "message": "Missing or invalid API key"})
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response, 401
        payload = request.get_json(silent=True) or {}
        result, status = add_event(payload)
        if status in (200, 201):
            invalidate_cache()
        response = jsonify(result)
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response, status

    @app.route("/mcp", methods=["GET", "POST", "DELETE", "OPTIONS"])
    def mcp_endpoint():
        if request.method == "OPTIONS":
            return _cors_preflight()
        session_id = request.headers.get("Mcp-Session-Id") or str(uuid.uuid4())
        if request.method == "DELETE":
            return Response(status=204, headers={"Access-Control-Allow-Origin": "*"})
        if request.method == "GET":
            body = {
                "name": "sproutme",
                "transport": "streamable_http",
                "protocol": DEFAULT_PROTOCOL,
                "openapi": f"{public_base_url}/openapi.json",
                "tools": [tool["name"] for tool in MCP_TOOLS],
            }
            if authorized_for_write():
                body["tools"] = body["tools"] + [tool["name"] for tool in MCP_WRITE_TOOLS]
            response = jsonify(body)
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Mcp-Session-Id"] = session_id
            return response

        message = request.get_json(silent=True)
        if message is None:
            return _mcp_response(_jsonrpc_error(None, -32700, "Parse error"), session_id)

        if isinstance(message, list):
            payloads = [handle_mcp_message(item, cached_events, get_event, add_event, authorized_for_write, invalidate_cache, session_id) for item in message]
            payloads = [item for item in payloads if item is not None]
            return _mcp_response(payloads if payloads else None, session_id)

        payload = handle_mcp_message(message, cached_events, get_event, add_event, authorized_for_write, invalidate_cache, session_id)
        if payload is None:
            return _mcp_response(None, session_id)
        return _mcp_response(payload, session_id)

    return app


def _cors_preflight():
    return Response(
        status=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization, Mcp-Session-Id, MCP-Protocol-Version",
            "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        },
    )


def handle_mcp_message(message, cached_events, get_event, add_event, authorized_for_write, invalidate_cache, session_id):
    if not isinstance(message, dict):
        return _jsonrpc_error(None, -32600, "Invalid Request")

    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}

    if method == "notifications/initialized" or (method and method.startswith("notifications/") and msg_id is None):
        return None

    if method == "initialize":
        requested = (params.get("protocolVersion") or DEFAULT_PROTOCOL)
        protocol = requested if requested in PROTOCOL_VERSIONS else DEFAULT_PROTOCOL
        return _jsonrpc_result(msg_id, {
            "protocolVersion": protocol,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "sproutme", "version": "1.0.0"},
            "instructions": (
                "SproutMe EDM catalog. Tools return compact evidence JSON — you narrate. "
                "Never invent shows. search_events for city/genre/date; find_artist_shows for artists. "
                "If data is empty, use later or miss_reason."
            ),
        })

    if method == "ping":
        return _jsonrpc_result(msg_id, {})

    if method == "tools/list":
        tools = list(MCP_TOOLS)
        if authorized_for_write():
            tools = tools + list(MCP_WRITE_TOOLS)
        return _jsonrpc_result(msg_id, {"tools": tools})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            text, is_error = call_tool(name, arguments, cached_events, get_event, add_event, authorized_for_write, invalidate_cache)
        except Exception as exc:
            text, is_error = f"Tool error: {exc}", True
        return _jsonrpc_result(msg_id, {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        })

    if msg_id is None:
        return None
    return _jsonrpc_error(msg_id, -32601, f"Method not found: {method}")


def call_tool(name, arguments, cached_events, get_event, add_event, authorized_for_write, invalidate_cache):
    if name == "search_events":
        result = filter_events(
            cached_events(),
            q=arguments.get("q"),
            city=arguments.get("city"),
            genre=arguments.get("genre"),
            date=arguments.get("date"),
            limit=arguments.get("limit", DEFAULT_LIMIT),
        )
        return json.dumps(result, indent=2), False

    if name == "find_artist_shows":
        result = find_artist_shows(
            cached_events(),
            artist=arguments.get("artist") or arguments.get("q") or "",
            city=arguments.get("city"),
            date=arguments.get("date"),
            limit=arguments.get("limit", 5),
        )
        return json.dumps(result, indent=2), False

    if name == "get_event":
        event_id = arguments.get("event_id")
        try:
            event_id = int(event_id)
        except (TypeError, ValueError):
            return "event_id must be an integer", True
        event = compact_event(get_event(event_id))
        if not event:
            return f"No event found with id {event_id}", True
        return json.dumps(event, indent=2), False

    if name == "add_event":
        if not authorized_for_write():
            return "Missing or invalid API key", True
        result, status = add_event(arguments)
        if status in (200, 201) and result.get("success"):
            invalidate_cache()
            return json.dumps(compact_event(result.get("data")) or result, indent=2), False
        return result.get("message") or "Could not add event", True

    return f"Unknown tool: {name}", True
