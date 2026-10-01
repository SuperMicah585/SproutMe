import json
import os
import re
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from services.public_api import clean_event_url

TICKETMASTER_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
TICKETMASTER_CITIES = (
    ("San Francisco", "US"),
    ("Oakland", "US"),
    ("San Jose", "US"),
    ("Los Angeles", "US"),
    ("San Diego", "US"),
    ("Seattle", "US"),
    ("Portland", "US"),
    ("Denver", "US"),
    ("Chicago", "US"),
    ("Detroit", "US"),
    ("Atlanta", "US"),
    ("Miami", "US"),
    ("Washington", "US"),
    ("Austin", "US"),
    ("Dallas", "US"),
    ("Houston", "US"),
    ("Phoenix", "US"),
    ("Las Vegas", "US"),
    ("Boston", "US"),
    ("New York", "US"),
    ("Brooklyn", "US"),
    ("Vancouver", "CA"),
)
DANCE_CLASSIFICATIONS = ("Dance/Electronic", "House", "Techno")


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value):
    text = _clean(value).lower()
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def event_identity(rec):
    url = _clean(rec.get("event_url") or rec.get("event_link_url")).split("?")[0].lower()
    name = _norm(rec.get("event_name"))[:48]
    venue = _norm(rec.get("venue"))[:40]
    day = _clean(rec.get("raw_date") or rec.get("date"))[:10].replace("-", "/")
    return (url or None, name, venue, day)


def is_duplicate(left, right):
    try:
        from services.catalog_normalize import events_are_duplicates
    except ImportError:
        from catalog_normalize import events_are_duplicates
    if events_are_duplicates(left, right):
        return True
    # Fallback for rows that lack venue city paren formatting.
    left_url, left_name, left_venue, left_day = event_identity(left)
    right_url, right_name, right_venue, right_day = event_identity(right)
    if left_url and right_url and left_url == right_url:
        return True
    if left_day and right_day and left_day == right_day:
        if left_venue and left_venue == right_venue:
            if left_name and (left_name in right_name or right_name in left_name):
                return True
            if left_name and right_name and left_name[:18] == right_name[:18]:
                return True
    return False


def merge_event_catalog(existing, incoming):
    merged = list(existing or [])
    added = []
    for rec in incoming or []:
        if any(is_duplicate(rec, current) for current in merged):
            continue
        merged.append(rec)
        added.append(rec)
    return merged, added


def _http_json(url, timeout=20):
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _genre_from_tm(event):
    tags = []
    seen = set()
    for item in event.get("classifications") or []:
        for key in ("genre", "subGenre"):
            name = _clean((item.get(key) or {}).get("name")).lower()
            if not name or name in {"undefined", "other"} or name in seen:
                continue
            seen.add(name)
            tags.append(name)
            if len(tags) >= 4:
                return ", ".join(tags)
    return ", ".join(tags) or "electronic"


def _ticket_from_tm(event):
    prices = []
    for item in event.get("priceRanges") or []:
        try:
            amount = float(item.get("min"))
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            prices.append("free")
        else:
            prices.append(f"${int(amount)}" if amount.is_integer() else f"${amount:.2f}".rstrip("0").rstrip("."))
    status = ((event.get("dates") or {}).get("status") or {}).get("code") or ""
    if status.lower() == "offsale":
        return prices[0] if prices else ""
    return prices[0] if prices else ""


def _map_ticketmaster_event(event):
    venues = ((event.get("_embedded") or {}).get("venues") or [{}])
    venue = venues[0] if venues else {}
    city = _clean((venue.get("city") or {}).get("name"))
    venue_name = _clean(venue.get("name"))
    local_date = _clean(((event.get("dates") or {}).get("start") or {}).get("localDate"))
    raw_date = local_date.replace("-", "/") if local_date else ""
    attractions = ((event.get("_embedded") or {}).get("attractions") or [])
    headliners = [_clean(item.get("name")) for item in attractions if _clean(item.get("name"))]
    organizer = _clean((event.get("promoter") or {}).get("name")) or (headliners[0] if headliners else "")
    event_name = _clean(event.get("name"))
    if headliners and event_name and headliners[0].lower() not in event_name.lower():
        event_name = f"{event_name} w/ {', '.join(headliners[:2])}"
    formatted_venue = f"{venue_name} ({city})" if venue_name and city else venue_name
    try:
        from services.catalog_normalize import normalize_event, serialize_headliners
    except ImportError:
        from catalog_normalize import normalize_event, serialize_headliners
    headliner = serialize_headliners(headliners, limit=3) if headliners else ""
    row = {
        "date": raw_date,
        "event_name": event_name,
        "event_url": clean_event_url(_clean(event.get("url"))),
        "venue": formatted_venue,
        "city": city,
        "genre": _genre_from_tm(event),
        "ticket_info": _ticket_from_tm(event),
        "organizer": organizer,
        "event_link_url": clean_event_url(_clean(event.get("url"))),
        "event_link_text": "Tickets",
        "raw_date": raw_date,
        "headliner": headliner,
        "_skip_enrich": True,
        "_source": {
            "event_name": event_name,
            "venue": formatted_venue,
            "raw_date": raw_date,
            "provider": "ticketmaster",
        },
    }
    return normalize_event(row)


def fetch_ticketmaster_events(api_key=None, cities=None, max_pages=2):
    api_key = (api_key or os.environ.get("TICKETMASTER_API_KEY") or "").strip()
    if not api_key:
        print("TICKETMASTER_API_KEY is not set; skipping Ticketmaster catalog.")
        return []
    start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen_ids = set()
    records = []
    cities = cities or TICKETMASTER_CITIES
    for city, country in cities:
        for classification in DANCE_CLASSIFICATIONS:
            for page in range(max_pages):
                params = {
                    "apikey": api_key,
                    "city": city,
                    "countryCode": country,
                    "classificationName": classification,
                    "startDateTime": start,
                    "size": 100,
                    "page": page,
                    "sort": "date,asc",
                }
                url = f"{TICKETMASTER_URL}?{urlencode(params)}"
                try:
                    payload = _http_json(url)
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                    print(f"Ticketmaster fetch failed for {city} {classification} p{page}: {exc}")
                    break
                events = ((payload.get("_embedded") or {}).get("events") or [])
                if not events:
                    break
                for event in events:
                    event_id = event.get("id")
                    if not event_id or event_id in seen_ids:
                        continue
                    seen_ids.add(event_id)
                    mapped = _map_ticketmaster_event(event)
                    if mapped.get("event_name") and mapped.get("raw_date"):
                        records.append(mapped)
                page_info = (payload.get("page") or {})
                if page + 1 >= int(page_info.get("totalPages") or 1):
                    break
                time.sleep(0.25)
            time.sleep(0.2)
        print(f"Ticketmaster {city}: catalog now {len(records)} unique events.")
    return records
