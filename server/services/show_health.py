import logging
import time

from services.artist_heat import heat_breakout, heat_popularity, load_heat_index, match_heat
from services.spotify_service import headliners_for_event
from services.venue_places import load_place_index, venue_key, venue_parts, venue_score

logger = logging.getLogger(__name__)

ARTIST_WEIGHT = 0.34
HEAT_WEIGHT = 0.34
VENUE_WEIGHT = 0.20
INDEX_TTL_SECONDS = 300

_index_cache = {"at": 0.0, "heat": None, "venues": None}


def _unit(value, scale):
    if value is None:
        return None
    try:
        return min(max(float(value) / scale, 0.0), 1.0)
    except (TypeError, ValueError):
        return None


def score_show(artist_pop=None, breakout=None, venue_score_raw=None):
    """Weighted SproutMe score. Missing inputs are dropped and the rest are rescaled to 1.0."""
    pieces = []
    artist = _unit(artist_pop, 100.0)
    hot = _unit(breakout, 8.0)
    venue = _unit(venue_score_raw, 10.0)
    if artist is not None:
        pieces.append(("artist", ARTIST_WEIGHT, artist))
    if hot is not None:
        pieces.append(("hot", HEAT_WEIGHT, hot))
    if venue is not None:
        pieces.append(("venue", VENUE_WEIGHT, venue))
    parts = {name: round(value, 3) for name, _weight, value in pieces}
    total_weight = sum(weight for _name, weight, _value in pieces)
    if total_weight <= 0:
        return 0.0, parts
    score = sum(weight * value for _name, weight, value in pieces) / total_weight
    return score, parts


def display_score(score):
    try:
        ratio = float(score or 0)
    except (TypeError, ValueError):
        ratio = 0.0
    return int(round(min(max(ratio, 0.0), 1.0) * 100))


def _match_place_exact(index, venue, city=""):
    if not index:
        return None
    name, city = venue_parts(venue, city)
    key = venue_key(name, city)
    if not key:
        return None
    return (index.get("by_key") or {}).get(key)


def _load_indexes(list_heat, list_venues):
    now = time.time()
    if (
        _index_cache["heat"] is not None
        and _index_cache["venues"] is not None
        and now - _index_cache["at"] < INDEX_TTL_SECONDS
    ):
        return _index_cache["heat"], _index_cache["venues"]
    heat_rows = []
    venue_rows = []
    if list_heat:
        try:
            heat_rows = list_heat() or []
        except Exception as exc:
            logger.warning("artist heat cache load failed: %s", exc)
    if list_venues:
        try:
            venue_rows = list_venues() or []
        except Exception as exc:
            logger.warning("venue place cache load failed: %s", exc)
    _index_cache["heat"] = load_heat_index(heat_rows) or {}
    _index_cache["venues"] = load_place_index(venue_rows) or {"rows": [], "by_key": {}}
    _index_cache["at"] = now
    return _index_cache["heat"], _index_cache["venues"]


def annotate_events(events, list_heat=None, list_venues=None):
    if not events:
        return events
    try:
        heat, venues = _load_indexes(list_heat, list_venues)
    except Exception as exc:
        logger.warning("sprout score indexes failed: %s", exc)
        return events
    for event in events:
        if not isinstance(event, dict):
            continue
        artists = headliners_for_event(event, limit=3)
        place = _match_place_exact(venues, event.get("venue") or "", event.get("city") or "")
        venue_raw = venue_score(place) if place and place.get("place_id") else None
        if place and place.get("place_id"):
            if place.get("lat") is not None:
                event["lat"] = place.get("lat")
            else:
                event.pop("lat", None)
            if place.get("lng") is not None:
                event["lng"] = place.get("lng")
            else:
                event.pop("lng", None)
            place_name = (place.get("display_name") or "").strip()
            if place_name:
                event["place_name"] = place_name
            else:
                event.pop("place_name", None)
        else:
            event.pop("lat", None)
            event.pop("lng", None)
            event.pop("place_name", None)
        # Unmatched artists count as popularity 0 (not "missing"), so venue
        # alone cannot rescale into a high SproutMe score.
        # Multi-act bills: keep the best artist/heat contribution.
        best_score = None
        best_parts = {}
        if not artists:
            artists = [""]
        for artist in artists:
            row = match_heat(heat, artist) if artist else None
            score, parts = score_show(
                heat_popularity(row) if row else 0,
                heat_breakout(row) if row else None,
                venue_raw,
            )
            if best_score is None or score > best_score:
                best_score = score
                best_parts = parts
        event["sprout_parts"] = best_parts
        if best_parts:
            event["sprout_score"] = display_score(best_score)
        else:
            event.pop("sprout_score", None)
            event.pop("health", None)
    return events
