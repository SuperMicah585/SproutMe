"""Deterministic catalog cleaning that runs on every daily scrape wipe+insert.

Suburbs stay as their own city values for web facets. Metro expansion is for
search (SMS / geo) via metro_cities().
"""
from __future__ import annotations

import json
import re

HEADLINER_JUNK_RE = re.compile(
    r"\b("
    r"20\d{2}|north america|south america|latin america|"
    r"europe|asia|australia|world\s*tour|tour|presents|"
    r"festival|fest\b|campout|day party|night party|"
    r"afterlife|farewell|open to close|takeover"
    r")\b",
    re.I,
)

CITY_TYPOS = {
    "bimingham": "Birmingham",
    "vanvouer": "Vancouver",
    "des moines": "Des Moines",
    "los angeles": "Los Angeles",
    "san francisco": "San Francisco",
    "las vegas": "Las Vegas",
    "san diego": "San Diego",
    "new york": "New York",
    "washington": "Washington",
}

# Region / venue-shell labels that should not be stored as city when a better
# city can be peeled from the venue string.
REGION_CITIES = {
    "socal",
    "norcal",
    "bay area",
    "east bay",
    "south bay",
    "inland empire",
    "northern california",
    "southern california",
    "texas",
    "massachusetts",
    "iowa",
    "nebraska",
    "oregon",
    "warehouse",
    "fairgrounds",
    "catacombs",
    "sequoia forest",
}

# Venue-name aliases keyed by normalized name (city-agnostic).
VENUE_ALIASES = {
    "exchangela": "Exchange",
    "exchange": "Exchange",
    "thenovobymicrosoft": "The Novo",
    "thenovo": "The Novo",
    "foxtheateroakland": "Fox Theater",
    "foxtheater": "Fox Theater",
    "academylanightclub": "Academy",
    "academyla": "Academy",
    "academynightclub": "Academy",
    "meowwolfdenverconvergencestation": "Meow Wolf",
    "meowwolfdenver": "Meow Wolf",
    "meowwolf": "Meow Wolf",
}

GENRE_ALIASES = {
    "drum & bass": "drum and bass",
    "drum n bass": "drum and bass",
    "dnb": "drum and bass",
    "hip hop": "hip-hop",
    "hiphop": "hip-hop",
    "r & b": "rnb",
    "r and b": "rnb",
}

# Metro buckets: parent -> siblings (including parent). Suburbs keep their own
# stored city; search expands via metro_cities().
METRO_GROUPS = {
    "los angeles": [
        "Los Angeles", "West Hollywood", "Hollywood", "Santa Monica", "Venice",
        "Malibu", "Pasadena", "Pomona", "Anaheim", "Van Nuys", "Inglewood",
        "Long Beach", "Burbank", "Carson", "Rowland Heights", "Playa Del Rey",
        "Redondo Beach", "Monterey Park", "Lake View Terrace", "DTLA",
    ],
    "san francisco": [
        "San Francisco", "Oakland", "Berkeley", "San Jose", "Alameda",
        "Campbell", "Mountain View", "Milpitas", "West Oakland", "East Bay",
    ],
    "seattle": [
        "Seattle", "Tacoma", "Bellevue", "Redmond", "Kirkland", "Everett",
        "Shoreline", "Renton", "Tukwila", "George", "Bothell",
    ],
    "washington": [
        "Washington", "Silver Spring", "Arlington", "Alexandria", "Falls Church",
    ],
    "miami": [
        "Miami", "Miami Beach", "Wynwood", "Little Haiti", "Hialeah",
        "Fort Lauderdale", "West Palm Beach", "Boca Raton", "Oakland Park",
    ],
    "chicago": [
        "Chicago", "Bedford Park", "Evanston", "Oak Park", "Palatine",
        "Libertyville", "Highland Park",
    ],
    "denver": [
        "Denver", "Aurora", "Boulder", "Englewood", "Nederland",
    ],
    "vancouver": [
        "Vancouver", "East Vancouver", "Burnaby", "Surrey", "Abbotsford",
        "Whistler", "Victoria", "Kelowna",
    ],
}

# Suburb -> parent key (lowercase).
METRO_PARENT = {}
for _parent, _cities in METRO_GROUPS.items():
    for _city in _cities:
        METRO_PARENT[_city.lower()] = _parent


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _norm_key(value):
    text = _clean(value).lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _title_city(value):
    text = _clean(value)
    if not text:
        return ""
    if text.lower() in CITY_TYPOS:
        return CITY_TYPOS[text.lower()]
    # Preserve known multi-word casing from typos map misses via title().
    if text.isupper() and len(text) > 3:
        text = text.title()
    return text


def city_from_venue(venue):
    text = _clean(venue)
    match = re.search(r"\(([^)]+)\)\s*$", text)
    if not match:
        return ""
    raw = _clean(match.group(1)).split(",")[0].split("/")[0].strip()
    if not raw or len(raw) > 40:
        return ""
    if re.search(r"\d+\+|all ages|capacity|\b20\d{2}\b", raw, re.I):
        return ""
    return _title_city(raw)


def is_region_city(city):
    text = _clean(city)
    if not text:
        return True
    lowered = text.lower()
    if " / " in text or " bay area" in lowered:
        return True
    return lowered in REGION_CITIES


def city_from_venue_body(venue):
    """Pull a city token from venue text when paren is a region shell."""
    text = _clean(venue)
    # Common patterns: "TBA - Los Angeles (...)", "Something Los Angeles"
    match = re.search(
        r"(?:^|[\s\-–,|/])("
        r"Los Angeles|San Francisco|San Diego|Las Vegas|New York|Chicago|"
        r"Seattle|Portland|Denver|Miami|Atlanta|Boston|Dallas|Houston|"
        r"Oakland|Berkeley|Vancouver|Washington|Detroit|Austin|Phoenix"
        r")(?:\s|$|\(|,)",
        text,
        flags=re.I,
    )
    if match:
        return _title_city(match.group(1))
    return ""


def canonical_city(city, venue=""):
    """Fix typos / casing; replace region shells using venue when possible."""
    venue_city = city_from_venue(venue)
    body_city = city_from_venue_body(venue)
    text = _clean(city)
    if not text or is_region_city(text):
        for candidate in (venue_city, body_city):
            if candidate and not is_region_city(candidate):
                return _title_city(candidate)
        return ""
    fixed = CITY_TYPOS.get(text.lower()) or _title_city(text)
    if is_region_city(fixed):
        for candidate in (venue_city, body_city):
            if candidate and not is_region_city(candidate):
                return _title_city(candidate)
        return ""
    return fixed


def metro_parent(city):
    key = _clean(city).lower()
    if not key:
        return ""
    return METRO_PARENT.get(key, "")


def metro_cities(city):
    """Return canonical city names in the same metro (including self)."""
    parent = metro_parent(city)
    if not parent:
        canon = canonical_city(city)
        return [canon] if canon else []
    return list(METRO_GROUPS.get(parent, []))


def normalize_venue_name(name):
    text = _clean(name)
    if not text:
        return ""
    # Drop trailing city already in name before paren formatting.
    text = re.split(r"\s*\(", text, maxsplit=1)[0].strip()
    text = re.split(
        r"(?:\$\s*\d|20\d{2}\s*/|\b(?:facebook|instagram|ticketweb)\b)",
        text,
        maxsplit=1,
        flags=re.I,
    )[0].strip(" ,;-@")
    alias = VENUE_ALIASES.get(_norm_key(text))
    if alias:
        return alias
    # Strip " - City" / " at Place" noise when it duplicates branding.
    stripped = re.sub(r"\s+-\s+(Oakland|LA|Los Angeles|Denver|SF)\b", "", text, flags=re.I).strip()
    alias = VENUE_ALIASES.get(_norm_key(stripped))
    if alias:
        return alias
    return stripped or text


def format_venue(name, city):
    venue_name = normalize_venue_name(name) or _clean(name)
    city = canonical_city(city, f"{venue_name} ({city})" if city else venue_name)
    if not venue_name:
        return ""
    if city and f"({city.lower()})" not in venue_name.lower():
        return f"{venue_name} ({city})"
    return venue_name


def venue_dedupe_key(venue, city=""):
    """Stable venue identity: strip city suffixes, 'the', and room tags."""
    name = normalize_venue_name(venue)
    city = canonical_city(city, venue)
    if not name:
        return ""
    # Drop trailing " - City" / " City" when city is known.
    if city:
        city_re = re.escape(city)
        name = re.sub(rf"\s*[-–,/]\s*{city_re}\b.*$", "", name, flags=re.I).strip()
        name = re.sub(rf"\s+{city_re}\b.*$", "", name, flags=re.I).strip()
    name = re.sub(r"^the\s+", "", name, flags=re.I).strip()
    # Room / wing noise: "White Oak Music Hall - Downstairs"
    name = re.sub(
        r"\s*[-–]\s*(downstairs|upstairs|main\s*room|lounge|outdoor|"
        r"amphitheatre|amphitheater|ballroom)\b.*$",
        "",
        name,
        flags=re.I,
    ).strip()
    # "Mohawk-Austin" style city glued with hyphen after strip failed.
    name = re.sub(r"[-–]([A-Za-z]+)$", "", name).strip() or name
    return f"{_norm_key(city)}|{_norm_key(name)}"


def event_name_artists(name):
    """Artist tokens from an event title for soft duplicate matching."""
    text = _clean(name)
    if not text:
        return frozenset()
    text = re.sub(
        r"\((?:\d+\+[^)]*|all\s*ages?|ages?\s*\d+\+?)\)",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b\d+\+\b", " ", text)
    text = re.sub(r"\bevent\b", " ", text, flags=re.I)
    text = re.sub(
        r"\s*(?:w/|with|feat\.?|featuring|x|\+|vs\.?|&|/)\s*",
        ",",
        text,
        flags=re.I,
    )
    text = text.replace(";", ",")
    tokens = []
    seen = set()
    for part in re.split(r"[,|]+", text):
        token = re.sub(r"[^a-z0-9]+", "", part.lower())
        if not token or len(token) < 2:
            continue
        if token in {"and", "the", "live", "dj", "presents", "tour"}:
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return frozenset(tokens)


def artists_overlap(left, right):
    """True when artist sets equal, one contains the other, or share a headliner."""
    a = event_name_artists(left) if not isinstance(left, (set, frozenset)) else left
    b = event_name_artists(right) if not isinstance(right, (set, frozenset)) else right
    if not a or not b:
        return False
    if a == b or a.issubset(b) or b.issubset(a):
        return True
    return bool(a & b)


def sanitize_headliners(artists, limit=3):
    """Drop tour/festival fragments; keep short artist-like names."""
    cleaned = []
    seen = set()
    for raw in artists or []:
        text = _clean(raw).strip(" -|/,")
        if not text:
            continue
        if text.lower() in {"null", "none", "n/a", "tba", "tbd", "unknown"}:
            continue
        if HEADLINER_JUNK_RE.search(text):
            continue
        if len(text) > 40:
            continue
        # Reject bare region fragments.
        if re.fullmatch(r"(north|south|latin)\s+american?", text, flags=re.I):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def serialize_headliners(artists, limit=3):
    parts = sanitize_headliners(artists, limit=limit)
    if not parts:
        return ""
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def parse_headliners(value, limit=3):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return sanitize_headliners(value, limit=limit)
    text = _clean(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = None
        if isinstance(parsed, list):
            return sanitize_headliners(parsed, limit=limit)
    return sanitize_headliners(re.split(r"\s*,\s*", text), limit=limit)


def normalize_genre_tags(genre, max_tags=4):
    text = _clean(genre)
    if not text or text.lower() in {"null", "none", "n/a", "nan", "undefined"}:
        return ""
    parts = re.split(r"[,/;|]+", text)
    tags = []
    seen = set()
    for part in parts:
        tag = re.sub(r"\s+", " ", part.strip().lower()).strip(" .")
        if not tag:
            continue
        tag = GENRE_ALIASES.get(tag, tag)
        if tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
        if len(tags) >= max_tags:
            break
    return ", ".join(tags)


def event_dedupe_key(rec):
    """Legacy exact key; prefer soft dedupe via dedupe_event_records."""
    artists = event_name_artists(rec.get("event_name") or "")
    if not artists:
        artists = event_name_artists(
            " ".join(parse_headliners(rec.get("headliner")))
        )
    name = "|".join(sorted(artists)) if artists else _clean(rec.get("event_name")).lower()
    date = _clean(rec.get("raw_date") or rec.get("date"))[:10]
    vkey = venue_dedupe_key(rec.get("venue") or "", rec.get("city") or "")
    return f"{name}|{date}|{vkey}"


def _event_day(rec):
    return _clean(rec.get("raw_date") or rec.get("date"))[:10].replace("-", "/")


def _event_artists(rec):
    artists = event_name_artists(rec.get("event_name") or "")
    if artists:
        return artists
    return event_name_artists(" ".join(parse_headliners(rec.get("headliner"))))


def events_are_duplicates(left, right):
    """Same calendar day + venue, with overlapping artist identity."""
    if not left or not right:
        return False
    day_l, day_r = _event_day(left), _event_day(right)
    if not day_l or not day_r or day_l != day_r:
        return False
    v_l = venue_dedupe_key(left.get("venue") or "", left.get("city") or "")
    v_r = venue_dedupe_key(right.get("venue") or "", right.get("city") or "")
    if not v_l or not v_r or v_l != v_r:
        return False
    # Same ticket / event URL is always a duplicate.
    url_l = _clean(left.get("event_url") or left.get("event_link_url")).split("?")[0].lower()
    url_r = _clean(right.get("event_url") or right.get("event_link_url")).split("?")[0].lower()
    if url_l and url_r and url_l == url_r:
        return True
    return artists_overlap(_event_artists(left), _event_artists(right))


def _row_quality(rec):
    score = 0
    if parse_headliners(rec.get("headliner")):
        score += 4
    url = _clean(rec.get("event_url") or rec.get("event_link_url")).lower()
    if url and "instagram.com" not in url and "facebook.com" not in url:
        score += 3
    elif url:
        score += 1
    if _clean(rec.get("ticket_info")):
        score += 1
    if _clean(rec.get("genre")):
        score += 1
    venue = _clean(rec.get("venue")).lower()
    if venue and not venue.startswith("tba"):
        score += 2
    # Prefer richer titles (support acts listed) over bare headliner names.
    artists = _event_artists(rec)
    if artists:
        score += min(3, len(artists))
    name = _clean(rec.get("event_name"))
    if re.search(r"\d+\+|all\s*ages", name, re.I):
        score -= 1
    return score


def dedupe_event_records(records):
    """Collapse near-duplicates in one scrape batch; prefer richer rows.

    Groups by day+venue first, then merges rows whose artist sets overlap
    (e.g. 'Bassvictim' vs 'Bassvictim w/ Thoom' at the same Showbox night).
    """
    groups = {}
    group_order = []
    for rec in records or []:
        day = _event_day(rec)
        vkey = venue_dedupe_key(rec.get("venue") or "", rec.get("city") or "")
        bucket = f"{day}|{vkey}" if day and vkey else f"unique|{id(rec)}"
        if bucket not in groups:
            groups[bucket] = []
            group_order.append(bucket)
        groups[bucket].append(rec)

    out = []
    for bucket in group_order:
        cluster = groups[bucket]
        if len(cluster) == 1 or bucket.startswith("unique|"):
            out.extend(cluster)
            continue
        kept = []
        for rec in cluster:
            matched = False
            for i, existing in enumerate(kept):
                if events_are_duplicates(rec, existing):
                    a_new = len(_event_artists(rec))
                    a_old = len(_event_artists(existing))
                    q_new, q_old = _row_quality(rec), _row_quality(existing)
                    # Prefer the fuller lineup, then richer metadata.
                    if a_new > a_old or (a_new == a_old and q_new > q_old):
                        kept[i] = rec
                    matched = True
                    break
            if not matched:
                kept.append(rec)
        out.extend(kept)
    return out


def normalize_event(rec):
    """Apply deterministic city/venue/genre/headliner cleaning in place."""
    if not isinstance(rec, dict):
        return rec

    venue_raw = rec.get("venue") or ""
    city_raw = rec.get("city") or ""
    venue_city = city_from_venue(venue_raw)
    city = canonical_city(city_raw, venue_raw)
    if venue_city and (not city or is_region_city(city_raw)):
        city = canonical_city(venue_city, venue_raw)

    name = normalize_venue_name(venue_raw) or _clean(venue_raw)
    rec["city"] = city
    rec["venue"] = format_venue(name, city) if name else _clean(venue_raw)

    if rec.get("event_name") is not None:
        rec["event_name"] = _clean(rec.get("event_name"))
    if rec.get("organizer") is not None:
        rec["organizer"] = _clean(rec.get("organizer"))

    if "genre" in rec:
        rec["genre"] = normalize_genre_tags(rec.get("genre"))

    raw_head = rec.get("headliner")
    artists = parse_headliners(raw_head)
    if artists:
        rec["headliner"] = serialize_headliners(artists)
    elif raw_head:
        # Junk headliner wiped so heuristic/LLM can refill.
        rec["headliner"] = ""

    return rec
