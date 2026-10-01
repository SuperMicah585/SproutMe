"""Neighborhood / area pins for SMS 'near Capitol Hill' style queries."""

from __future__ import annotations

import math
import re

# Seed pins for common EDM neighborhoods (lat, lng). Used when Places misses.
# Keep city keys lowercase canonical.
AREA_PINS = {
    ("capitol hill", "seattle"): (47.6253, -122.3222),
    ("cap hill", "seattle"): (47.6253, -122.3222),
    ("ballard", "seattle"): (47.6687, -122.3840),
    ("fremont", "seattle"): (47.6510, -122.3500),
    ("university district", "seattle"): (47.6615, -122.3130),
    ("u district", "seattle"): (47.6615, -122.3130),
    ("udistrict", "seattle"): (47.6615, -122.3130),
    ("belltown", "seattle"): (47.6145, -122.3447),
    ("pioneer square", "seattle"): (47.6015, -122.3340),
    ("sodo", "seattle"): (47.5805, -122.3330),
    ("so do", "seattle"): (47.5805, -122.3330),
    ("queen anne", "seattle"): (47.6370, -122.3560),
    ("georgetown", "seattle"): (47.5470, -122.3210),
    ("wallingford", "seattle"): (47.6600, -122.3340),
    ("greenwood", "seattle"): (47.6905, -122.3550),
    ("columbia city", "seattle"): (47.5590, -122.2860),
    ("west seattle", "seattle"): (47.5610, -122.3865),
    ("downtown", "seattle"): (47.6062, -122.3321),
    ("dtla", "los angeles"): (34.0407, -118.2468),
    ("hollywood", "los angeles"): (34.0928, -118.3287),
    ("silver lake", "los angeles"): (34.0869, -118.2702),
    ("echo park", "los angeles"): (34.0782, -118.2606),
    ("arts district", "los angeles"): (34.0412, -118.2325),
    ("mission", "san francisco"): (37.7599, -122.4148),
    ("soma", "san francisco"): (37.7786, -122.4056),
    ("haight", "san francisco"): (37.7692, -122.4481),
    ("williamsburg", "new york"): (40.7081, -73.9571),
    ("bushwick", "new york"): (40.6942, -73.9210),
    ("east village", "new york"): (40.7265, -73.9815),
    ("wicker park", "chicago"): (41.9088, -87.6796),
    ("logan square", "chicago"): (41.9295, -87.7080),
    ("wynwood", "miami"): (25.8010, -80.1990),
}

# Transit stations used for "near light rail / transit" filters (lat, lng).
# Distances are haversine miles to venue coords in venue_place_cache.
TRANSIT_STATIONS = {
    "seattle": [
        ("Northgate", 47.7057, -122.3285),
        ("Roosevelt", 47.6763, -122.3170),
        ("U District", 47.6602, -122.3135),
        ("Capitol Hill", 47.6195, -122.3203),
        ("Westlake", 47.6115, -122.3370),
        ("Symphony", 47.6085, -122.3355),
        ("Pioneer Square", 47.6025, -122.3310),
        ("Intl District", 47.5982, -122.3279),
        ("Stadium", 47.5915, -122.3270),
        ("SODO", 47.5803, -122.3275),
        ("Judkins Park", 47.5914, -122.3040),  # East Link / 2 Line
        ("Beacon Hill", 47.5792, -122.3119),
        ("Mount Baker", 47.5765, -122.2977),
        ("Columbia City", 47.5590, -122.2859),
        ("Othello", 47.5379, -122.2815),
        ("Rainier Beach", 47.5227, -122.2793),
        ("Tukwila Intl Blvd", 47.4642, -122.2882),
        ("SeaTac/Airport", 47.4445, -122.2970),
        ("Angle Lake", 47.4228, -122.2975),
        ("Bellevue Downtown", 47.6163, -122.1920),  # East Link
        ("Wilburton", 47.6130, -122.1780),
        ("Spring District", 47.6255, -122.1785),
        ("Redmond Tech", 47.6445, -122.1335),
    ],
    # TriMet MAX (approx platform centers) — enough for venue walkability filters.
    "portland": [
        ("Washington Park", 45.5108, -122.7165),
        ("Goose Hollow/SW Jefferson", 45.5205, -122.6928),
        ("Providence Park", 45.5212, -122.6915),
        ("Library/SW 9th Ave", 45.5203, -122.6838),
        ("Galleria/SW 10th Ave", 45.5198, -122.6815),
        ("Pioneer Square South", 45.5186, -122.6789),
        ("Pioneer Square North", 45.5192, -122.6789),
        ("Pioneer Courthouse/SW 6th", 45.5189, -122.6785),
        ("Pioneer Place/SW 5th", 45.5185, -122.6775),
        ("Mall/SW 4th", 45.5182, -122.6762),
        ("Morrison/SW 3rd", 45.5178, -122.6750),
        ("Yamhill District", 45.5165, -122.6755),
        ("Oak/SW 1st", 45.5200, -122.6718),
        ("Skidmore Fountain", 45.5225, -122.6710),
        ("Old Town/Chinatown", 45.5252, -122.6715),
        ("Union Station/NW 5th & Glisan", 45.5288, -122.6755),
        ("NW 6th & Davis", 45.5255, -122.6775),
        ("PSU Urban Center", 45.5120, -122.6840),
        ("PSU South", 45.5085, -122.6845),
        ("South Waterfront/S Moody", 45.4985, -122.6710),
        ("OMSI/SE Water", 45.5080, -122.6655),
        ("Clinton/SE 12th", 45.5032, -122.6545),
        ("Rose Quarter TC", 45.5308, -122.6658),
        ("Convention Center", 45.5285, -122.6615),
        ("Lloyd Center/NE 11th", 45.5300, -122.6548),
        ("Hollywood/NE 42nd", 45.5355, -122.6205),
        ("SE Powell Blvd", 45.4970, -122.6390),
        ("SE Holgate", 45.4905, -122.6395),
        ("Gateway/NE 99th TC", 45.5260, -122.5635),
        ("PDX Airport", 45.5875, -122.5925),
    ],
}

TRANSIT_RADIUS_MILES = 0.75
TRANSIT_EXPAND_MILES = 1.25

NEAR_PHRASE_RE = re.compile(
    r"\b(?:near|around|close to|by|walking distance (?:from|to)|walking from)\s+"
    r"(.+?)(?:\s+(?:in|tonight|today|tomorrow|this\s+(?:weekend|week|evening)|please|thanks)(?:\b|$)|[,.!?]|$)",
    re.I,
)
GOING_TO_RE = re.compile(
    r"\b(?:going(?:\s+to)?|headed(?:\s+to)?|i'?m in|im in|staying (?:in|near)|at)\s+"
    r"(.+?)(?:\s+(?:in|tonight|today|tomorrow|find|looking|any|for)(?:\b|$)|[,.!?]|$)",
    re.I,
)
IN_HOOD_RE = re.compile(
    r"\bin\s+([a-z][a-z0-9'’\-\s]{2,40}?)\s+(?:tonight|today|tomorrow|this\s+weekend|looking|find|for shows?)",
    re.I,
)

DEFAULT_RADIUS_MILES = 1.75
EXPANDED_RADIUS_MILES = 3.5


def _norm(value):
    text = re.sub(r"\s+", " ", str(value or "").lower()).strip()
    text = text.replace("'", "'").replace("'", "'")
    text = re.sub(r"[^a-z0-9\s\-]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _city_key(city):
    return _norm(city)


def haversine_miles(lat1, lng1, lat2, lng2):
    try:
        lat1 = float(lat1)
        lng1 = float(lng1)
        lat2 = float(lat2)
        lng2 = float(lng2)
    except (TypeError, ValueError):
        return None
    if abs(lat1) > 90 or abs(lat2) > 90:
        return None
    r = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def transit_stations_for_city(city=""):
    key = _city_key(city)
    if not key:
        return []
    if key in TRANSIT_STATIONS:
        return TRANSIT_STATIONS[key]
    # soft match e.g. "seattle wa"
    for city_key, stations in TRANSIT_STATIONS.items():
        if city_key in key or key in city_key:
            return stations
    return []


def nearest_transit_station(lat, lng, city="", stations=None):
    stations = stations if stations is not None else transit_stations_for_city(city)
    best = None
    for item in stations or []:
        if len(item) < 3:
            continue
        name, slat, slng = item[0], item[1], item[2]
        miles = haversine_miles(lat, lng, slat, slng)
        if miles is None:
            continue
        if best is None or miles < best[0]:
            best = (miles, name)
    return best


def match_station_by_name(query, city="", stations=None):
    """Fuzzy-match a user station/origin phrase to a known stop. Returns (name, lat, lng) or None."""
    needle = _norm(query)
    if not needle:
        return None
    needle = re.sub(r"\b(station|stop|link|max|light\s*rail|the)\b", " ", needle)
    needle = re.sub(r"\s+", " ", needle).strip()
    if len(needle) < 3:
        return None
    stations = stations if stations is not None else transit_stations_for_city(city)
    best = None
    for item in stations or []:
        if len(item) < 3:
            continue
        name, slat, slng = item[0], item[1], item[2]
        name_n = _norm(name)
        score = 0
        if needle == name_n or needle in name_n or name_n in needle:
            score = 100 - abs(len(name_n) - len(needle))
        else:
            # token overlap (judkins ↔ judkins park)
            n_toks = set(needle.split())
            m_toks = set(name_n.split())
            if not n_toks or not m_toks:
                continue
            overlap = len(n_toks & m_toks) / float(len(n_toks | m_toks))
            if overlap < 0.45:
                continue
            score = int(overlap * 80)
        if best is None or score > best[0]:
            best = (score, name, slat, slng)
    if not best or best[0] < 40:
        return None
    return best[1], best[2], best[3]


def seed_pin(area, city=""):
    area_n = _norm(area)
    city_n = _city_key(city)
    if not area_n:
        return None
    if city_n:
        hit = AREA_PINS.get((area_n, city_n))
        if hit:
            return {
                "label": area.strip(),
                "city": city.strip() or city_n.title(),
                "lat": hit[0],
                "lng": hit[1],
                "source": "seed",
            }
    # Ambiguous: unique area name across seeds
    matches = [(key, pin) for key, pin in AREA_PINS.items() if key[0] == area_n]
    if len(matches) == 1:
        (area_key, city_key), pin = matches[0]
        return {
            "label": area.strip(),
            "city": city_key.title(),
            "lat": pin[0],
            "lng": pin[1],
            "source": "seed",
        }
    if city_n:
        for (area_key, city_key), pin in AREA_PINS.items():
            if city_key == city_n and (area_n in area_key or area_key in area_n):
                return {
                    "label": area.strip(),
                    "city": city.strip() or city_key.title(),
                    "lat": pin[0],
                    "lng": pin[1],
                    "source": "seed",
                }
    return None


def clean_area_phrase(raw):
    text = re.sub(r"\s+", " ", str(raw or "")).strip(" .,!?;:")
    text = re.sub(
        r"\b(seattle|portland|los angeles|la|sf|san francisco|nyc|new york|chicago|denver|miami|vancouver)\b$",
        "",
        text,
        flags=re.I,
    ).strip(" .,")
    text = re.sub(
        r"\b(area|neighborhood|district|hood|nightlife|bars?|clubs?|venues?|shows?|music)\b$",
        "",
        text,
        flags=re.I,
    ).strip(" .,")
    return text


def extract_near_phrase(text):
    raw = str(text or "").strip()
    if not raw:
        return None
    for pattern in (NEAR_PHRASE_RE, GOING_TO_RE, IN_HOOD_RE):
        match = pattern.search(raw)
        if not match:
            continue
        area = clean_area_phrase(match.group(1))
        if len(area) < 3 or len(area.split()) > 6:
            continue
        # Skip if it looks like a pure city ask
        if _norm(area) in {
            "seattle", "portland", "los angeles", "san francisco", "new york",
            "chicago", "denver", "miami", "vancouver", "my city",
        }:
            continue
        return area
    # Bare known hood mention
    lowered = _norm(raw)
    for area_key, city_key in AREA_PINS:
        if re.search(rf"\b{re.escape(area_key)}\b", lowered):
            return area_key
    return None


def infer_city_for_area(area, fallback_city=""):
    area_n = _norm(area)
    matches = [city for (a, city) in AREA_PINS if a == area_n]
    resolved = matches[0].title() if len(set(matches)) == 1 else ""
    fallback = (fallback_city or "").strip()
    # Ignore fallback when it's the neighborhood itself (model stuffed hood into city).
    if fallback and _norm(fallback) != area_n:
        return fallback
    return resolved
