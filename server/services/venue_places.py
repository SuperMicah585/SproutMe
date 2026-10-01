import json
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join((
    "places.id",
    "places.displayName",
    "places.rating",
    "places.userRatingCount",
    "places.types",
    "places.editorialSummary",
    "places.reviewSummary",
    "places.reviews",
    "places.location",
    "places.formattedAddress",
))
PIN_FIELD_MASK = ",".join((
    "places.id",
    "places.displayName",
    "places.location",
    "places.formattedAddress",
    "places.types",
))
CACHE_TTL_DAYS = 180
MAX_FETCH_PER_RUN = 80
TABLE = "venue_place_cache"
REVIEW_TEXT_CHARS = 400
FETCH_PAUSE_SEC = 0.12
NOISE_TOKENS = {"the", "a", "an", "at", "of", "and", "in", "wa", "ca", "or", "tx", "ny", "bc"}
SISTER_MARKERS = {
    "sodo", "soho", "downstairs", "upstairs", "rooftop", "annex", "patio",
    "loft", "warehouse", "ballroom", "stadium", "arena", "amphitheatre",
    "amphitheater", "pavilion", "coliseum", "theatre", "theater",
}
MUSIC_TYPES = {
    "event_venue", "concert_hall", "live_music_venue", "night_club",
    "performing_arts_theater", "auditorium", "stadium", "athletic_field",
}
BAR_TYPES = {"bar", "restaurant", "cafe", "meal_takeaway"}
STADIUM_TYPES = {"stadium", "athletic_field", "arena"}


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm(value):
    text = _clean(value).lower()
    text = text.replace("theatre", "theater").replace("centre", "center")
    text = re.sub(r"\bso\s*do\b", "sodo", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def venue_parts(venue, city=""):
    venue = _clean(venue)
    city = _clean(city)
    paren = re.search(r"\(([^)]+)\)", venue)
    name = re.split(r"\s*\(", venue, maxsplit=1)[0].strip() or venue
    name = re.split(
        r"(?:\$\s*\d|20\d{2}\s*/|\b(?:facebook|instagram|ticketweb)\b)",
        name,
        maxsplit=1,
        flags=re.I,
    )[0].strip()
    if not city and paren:
        city = _clean(paren.group(1).split(",")[0])
    return name, city


def venue_key(venue, city=""):
    name, city = venue_parts(venue, city)
    if not name:
        return ""
    return f"{_norm(city)}|{_norm(name)}"


def _tokens(value, extra_drop=None):
    drop = set(NOISE_TOKENS)
    if extra_drop:
        drop.update(extra_drop)
    return [token for token in _norm(value).split() if token and token not in drop]


def _markers(tokens):
    return {token for token in tokens if token in SISTER_MARKERS}


def names_match(left, right, city=""):
    city_tokens = set(_tokens(city))
    left_tokens = _tokens(left, city_tokens)
    right_tokens = _tokens(right, city_tokens)
    if not left_tokens or not right_tokens:
        return False
    if _markers(left_tokens) != _markers(right_tokens):
        return False
    left_key = " ".join(left_tokens)
    right_key = " ".join(right_tokens)
    if left_key == right_key:
        return True
    if left_key in right_key or right_key in left_key:
        shorter, longer = (left_key, right_key) if len(left_key) <= len(right_key) else (right_key, left_key)
        extra = set(longer.split()) - set(shorter.split())
        if extra & SISTER_MARKERS:
            return False
        return True
    return SequenceMatcher(None, left_key, right_key).ratio() >= 0.86


def _is_music_place(types):
    types = set(types or [])
    if types & MUSIC_TYPES:
        return True
    if types & BAR_TYPES and not (types & MUSIC_TYPES):
        return False
    return False


def venue_score(place):
    if not place or not place.get("place_id"):
        return 0.0
    try:
        count = int(place.get("user_rating_count") or 0)
    except (TypeError, ValueError):
        count = 0
    score = math.log1p(min(max(count, 0), 2500))
    types = set(place.get("types") or [])
    if types & STADIUM_TYPES:
        score *= 0.35
    elif types & MUSIC_TYPES:
        score *= 1.2
    elif types & BAR_TYPES:
        score *= 0.5
    try:
        score += float(place.get("rating") or 0) * 0.05
    except (TypeError, ValueError):
        pass
    return score


def city_matches(wanted, got):
    left = _norm(wanted)
    right = _norm(got)
    if not left or not right:
        return False
    if left == right:
        return True
    return left in right or right in left


def rating_rank_score(place):
    if not place or not place.get("place_id"):
        return 0.0
    try:
        rating = float(place.get("rating") or 0)
    except (TypeError, ValueError):
        rating = 0.0
    try:
        count = int(place.get("user_rating_count") or 0)
    except (TypeError, ValueError):
        count = 0
    if rating <= 0 or count < 20:
        return 0.0
    score = rating * math.log1p(min(count, 2500))
    types = set(place.get("types") or [])
    if types & STADIUM_TYPES:
        score *= 0.35
    elif types & MUSIC_TYPES:
        score *= 1.15
    elif types & BAR_TYPES:
        score *= 0.45
    return score


def rank_places(index, city, limit=3):
    city = _clean(city)
    if not index or not city:
        return []
    try:
        limit = min(max(int(limit or 3), 1), 5)
    except (TypeError, ValueError):
        limit = 3
    seen = set()
    ranked = []
    for row in index.get("rows") or []:
        if not row.get("place_id"):
            continue
        if not city_matches(city, row.get("city") or ""):
            continue
        types = set(row.get("types") or [])
        if types & BAR_TYPES and not (types & MUSIC_TYPES):
            continue
        if types & STADIUM_TYPES and not (types & MUSIC_TYPES):
            continue
        if "performing_arts_theater" in types and "night_club" not in types:
            continue
        if types & {"amphitheatre", "amphitheater"}:
            continue
        label = " ".join(part for part in ((row.get("display_name") or ""), (row.get("venue") or "")) if part)
        if re.search(r"\b(amphitheatre|amphitheater|stadium|arena)\b", label, re.I):
            continue
        score = rating_rank_score(row)
        if score <= 0:
            continue
        place_id = row.get("place_id")
        if place_id in seen:
            continue
        seen.add(place_id)
        ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:limit]]


def _review_text(item):
    blob = item.get("text") or {}
    if isinstance(blob, dict):
        return _clean(blob.get("text"))
    return _clean(blob)


def _compact_reviews(place):
    rows = []
    for item in place.get("reviews") or []:
        text = _review_text(item)
        if not text:
            continue
        rows.append({
            "rating": item.get("rating"),
            "when": _clean(item.get("relativePublishTimeDescription")),
            "text": text[:REVIEW_TEXT_CHARS],
        })
        if len(rows) >= 5:
            break
    return rows


def _localized(blob):
    if isinstance(blob, dict):
        inner = blob.get("text")
        if isinstance(inner, dict):
            return _clean(inner.get("text"))
        return _clean(inner or blob.get("text"))
    return _clean(blob)


def _map_place(place):
    location = place.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")
    try:
        lat = float(lat) if lat is not None else None
        lng = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lat, lng = None, None
    return {
        "place_id": _clean(place.get("id")) or None,
        "display_name": _localized(place.get("displayName")) or None,
        "rating": place.get("rating"),
        "user_rating_count": place.get("userRatingCount"),
        "types": [item for item in (place.get("types") or []) if item],
        "editorial_summary": _localized(place.get("editorialSummary")) or None,
        "review_summary": _localized(place.get("reviewSummary")) or None,
        "reviews": _compact_reviews(place),
        "lat": lat,
        "lng": lng,
        "formatted_address": _clean(place.get("formattedAddress")) or None,
    }


def _pick_place(places, venue_name, city):
    ranked = []
    for place in places or []:
        mapped = _map_place(place)
        display = mapped.get("display_name") or ""
        if not names_match(venue_name, display, city):
            continue
        types = mapped.get("types") or []
        music = 0 if _is_music_place(types) else 1
        bar_only = 0 if (set(types) & BAR_TYPES and not (set(types) & MUSIC_TYPES)) else 1
        ratio = SequenceMatcher(None, " ".join(_tokens(venue_name)), " ".join(_tokens(display))).ratio()
        ranked.append((music, bar_only, -ratio, mapped))
    if ranked:
        ranked.sort(key=lambda item: item[:3])
        return ranked[0][-1]
    return None


def search_place(query, api_key=None, venue_name="", city=""):
    api_key = (api_key or os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()
    if not api_key:
        return {"error": "GOOGLE_PLACES_API_KEY is not set"}
    query = _clean(query)
    if not query:
        return {"error": "empty_query"}
    payload = json.dumps({"textQuery": query, "maxResultCount": 3, "languageCode": "en"}).encode("utf-8")
    req = Request(
        PLACES_SEARCH_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        return {"error": f"http_{exc.code}", "detail": detail}
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"error": str(exc)}
    places = body.get("places") or []
    if not places:
        return {"place_id": None, "types": [], "reviews": []}
    picked = _pick_place(places, venue_name or query, city)
    if picked:
        return picked
    return {"place_id": None, "types": [], "reviews": [], "unmatched": True}


def resolve_area_pin(area, city="", api_key=None):
    """Resolve a neighborhood/area string to lat/lng via Places (or None)."""
    from services.neighborhoods import seed_pin, infer_city_for_area, clean_area_phrase

    area = clean_area_phrase(area)
    if not area:
        return None
    city = _clean(city) or infer_city_for_area(area, city)
    seeded = seed_pin(area, city)
    if seeded:
        return seeded

    api_key = (api_key or os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()
    if not api_key:
        return None
    query = " ".join(part for part in (area, city, "neighborhood") if part)
    payload = json.dumps({"textQuery": query, "maxResultCount": 3, "languageCode": "en"}).encode("utf-8")
    req = Request(
        PLACES_SEARCH_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": PIN_FIELD_MASK,
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return seeded
    for place in body.get("places") or []:
        mapped = _map_place(place)
        if mapped.get("lat") is None or mapped.get("lng") is None:
            continue
        label = mapped.get("display_name") or area
        return {
            "label": label,
            "city": city or "",
            "lat": mapped["lat"],
            "lng": mapped["lng"],
            "source": "places",
            "place_id": mapped.get("place_id"),
            "formatted_address": mapped.get("formatted_address"),
        }
    return seeded


def _usable_room(name, city):
    if not name or not city:
        return False
    if len(name) > 64:
        return False
    if re.search(r"20\d{2}", name):
        return False
    if re.search(r"\b(tba|tbd)\b", name, re.I):
        return False
    return True


def unique_venues(records):
    seen = {}
    for rec in records or []:
        venue = rec.get("venue") or ""
        city = rec.get("city") or ""
        name, city = venue_parts(venue, city)
        if not _usable_room(name, city):
            continue
        key = venue_key(name, city)
        if not key or key in seen:
            continue
        seen[key] = {
            "venue_key": key,
            "venue": name,
            "city": city,
            "query": " ".join(part for part in (name, city) if part),
        }
    return list(seen.values())


def _parse_fetched_at(value):
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def _stale(row, now, ttl):
    fetched = _parse_fetched_at((row or {}).get("fetched_at"))
    if not fetched:
        return True
    # Re-fetch rooms that never got coordinates (older cache rows).
    if (row or {}).get("place_id") and ((row or {}).get("lat") is None or (row or {}).get("lng") is None):
        return True
    return fetched < now - ttl


def _lookup_rows(supabase, keys):
    wanted = set(keys)
    cached = {}
    start = 0
    page = 1000
    while True:
        try:
            response = (
                supabase.table(TABLE)
                .select("venue_key,fetched_at,lat,lng,place_id")
                .range(start, start + page - 1)
                .execute()
            )
        except Exception as exc:
            print(f"Venue place cache lookup failed: {exc}")
            break
        rows = response.data or []
        for row in rows:
            key = row.get("venue_key")
            if key in wanted:
                cached[key] = row
        if len(rows) < page:
            break
        start += page
    return cached


def place_cache_row(venue, city, place, stamp=None):
    name, city = venue_parts(venue, city)
    key = venue_key(name, city)
    if not key:
        return None
    stamp = stamp or datetime.now(timezone.utc).isoformat()
    return {
        "venue_key": key,
        "query": " ".join(part for part in (name, city) if part),
        "city": city or None,
        "venue": name,
        "place_id": place.get("place_id"),
        "display_name": place.get("display_name"),
        "rating": place.get("rating"),
        "user_rating_count": place.get("user_rating_count"),
        "types": place.get("types") or [],
        "editorial_summary": place.get("editorial_summary"),
        "review_summary": place.get("review_summary"),
        "reviews": place.get("reviews") or [],
        "lat": place.get("lat"),
        "lng": place.get("lng"),
        "fetched_at": stamp,
        "updated_at": stamp,
    }


def upsert_place_rows(supabase, rows):
    errors = 0
    for start in range(0, len(rows), 50):
        chunk = rows[start:start + 50]
        try:
            supabase.table(TABLE).upsert(chunk).execute()
        except Exception as exc:
            errors += len(chunk)
            print(f"Venue place cache save failed: {exc}")
    return errors


def refresh_venue_place_cache(
    supabase,
    records,
    api_key=None,
    ttl_days=CACHE_TTL_DAYS,
    max_fetch=MAX_FETCH_PER_RUN,
):
    api_key = (api_key or os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip()
    venues = unique_venues(records)
    if not venues:
        return {"venues": 0, "hits": 0, "fetched": 0, "errors": 0, "deferred": 0}
    if not api_key:
        print("GOOGLE_PLACES_API_KEY is not set; skipping venue place cache.")
        return {"venues": len(venues), "hits": 0, "fetched": 0, "errors": 0, "deferred": 0, "skipped": True}
    if not supabase:
        return {"venues": len(venues), "hits": 0, "fetched": 0, "errors": 0, "deferred": 0, "skipped": True}

    now = datetime.now(timezone.utc)
    ttl = timedelta(days=ttl_days)
    cached = _lookup_rows(supabase, [item["venue_key"] for item in venues])
    missing = [item for item in venues if item["venue_key"] not in cached]
    stale = [
        item for item in venues
        if item["venue_key"] in cached and _stale(cached.get(item["venue_key"]), now, ttl)
    ]
    todo = missing + stale
    if max_fetch is None:
        deferred = 0
    else:
        deferred = max(0, len(todo) - max_fetch)
        todo = todo[:max_fetch]
    hits = len(venues) - len(missing) - len(stale)
    print(
        f"Places plan: {len(venues)} unique rooms, {len(missing)} unseen, "
        f"{len(stale)} stale, {len(todo)} this run, {deferred} deferred."
    )
    fetched = 0
    errors = 0
    unmatched = 0
    rows = []
    stamp = now.isoformat()
    for index, item in enumerate(todo):
        place = search_place(item["query"], api_key=api_key, venue_name=item["venue"], city=item["city"])
        if place.get("error"):
            errors += 1
            print(f"Places lookup failed for {item['query']}: {place.get('error')}")
            continue
        fetched += 1
        if place.get("unmatched") or not place.get("place_id"):
            unmatched += 1
        row = place_cache_row(item["venue"], item["city"], place, stamp=stamp)
        if row:
            rows.append(row)
        if index + 1 < len(todo):
            time.sleep(FETCH_PAUSE_SEC)
        if (index + 1) % 10 == 0 or index + 1 == len(todo):
            print(f"Places fetched {index + 1}/{len(todo)}.")

    errors += upsert_place_rows(supabase, rows)

    print(
        f"Venue place cache: {len(venues)} unique rooms, {hits} fresh, "
        f"{fetched} fetched, {unmatched} unmatched, {deferred} deferred, "
        f"{errors} errors (ttl {ttl_days}d)."
    )
    return {
        "venues": len(venues),
        "hits": hits,
        "fetched": fetched,
        "unmatched": unmatched,
        "deferred": deferred,
        "errors": errors,
    }


def load_place_index(rows):
    index = []
    by_key = {}
    for row in rows or []:
        if not row.get("place_id"):
            continue
        index.append(row)
        key = row.get("venue_key")
        if key:
            by_key[key] = row
    return {"rows": index, "by_key": by_key}


def match_place(index, venue, city=""):
    if not index:
        return None
    name, city = venue_parts(venue, city)
    key = venue_key(name, city)
    exact = (index.get("by_key") or {}).get(key)
    if exact:
        return exact
    city_n = _norm(city)
    best = None
    best_ratio = 0.0
    for row in index.get("rows") or []:
        row_city = _norm(row.get("city") or "")
        if city_n and row_city and city_n != row_city:
            continue
        display = row.get("display_name") or row.get("venue") or ""
        listing = row.get("venue") or ""
        if not names_match(name, display, city) and not names_match(name, listing, city):
            continue
        ratio = SequenceMatcher(
            None,
            " ".join(_tokens(name, set(_tokens(city)))),
            " ".join(_tokens(display, set(_tokens(city)))),
        ).ratio()
        if ratio > best_ratio:
            best = row
            best_ratio = ratio
    return best
