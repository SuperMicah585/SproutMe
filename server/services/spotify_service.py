import json
import logging
import os
import re
import time
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"
# Dev Mode uses an unpublished rolling 30s window. ~12 search calls / 30s stays under it.
MIN_INTERVAL_SEC = 2.5
GENERIC_HEADLINERS = {
    "tba", "tbd", "dj pop up", "open decks", "day party", "night party",
    "afterparty", "after party", "block party", "rave", "secret location",
}


class SpotifyRateLimit(Exception):
    def __init__(self, retry_after=30, reason=None, detail=""):
        try:
            self.retry_after = max(int(retry_after or 30), 1)
        except (TypeError, ValueError):
            self.retry_after = 30
        self.reason = (reason or "").strip() or None
        super().__init__(
            detail or f"HTTP 429 retry_after={self.retry_after}s reason={self.reason}"
        )


def _http_json(url, *, method="GET", headers=None, data=None, timeout=12):
    req = Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        if exc.code == 429:
            retry = exc.headers.get("Retry-After") or "30"
            reason = None
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                payload = {}
            err = payload.get("error")
            if isinstance(err, dict):
                reason = err.get("reason")
            elif isinstance(payload.get("reason"), str):
                reason = payload.get("reason")
            try:
                retry_after = int(float(retry))
            except (TypeError, ValueError):
                retry_after = 30
            raise SpotifyRateLimit(retry_after, reason, body[:300])
        raise
    if not raw:
        return {}
    return json.loads(raw)


class SpotifyCatalog:
    def __init__(self, client_id=None, client_secret=None, access_token=None):
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self._static_token = (access_token or "").strip()
        self._token = self._static_token or None
        self._token_expires = 0.0
        self._last_call_at = 0.0
        self._blocked_until = 0.0

    @classmethod
    def from_env(cls):
        return cls(
            client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
            client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET"),
            access_token=os.environ.get("SPOTIFY_ACCESS_TOKEN"),
        )

    @property
    def enabled(self):
        return bool(self.client_id and self.client_secret) or bool(self._static_token)

    def _access_token(self):
        if self._token and time.time() < self._token_expires:
            return self._token
        if self.client_id and self.client_secret:
            body = urlencode({
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }).encode()
            payload = _http_json(
                TOKEN_URL,
                method="POST",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=body,
            )
            token = payload.get("access_token")
            if not token:
                raise RuntimeError(payload.get("error_description") or "spotify token failed")
            self._token = token
            self._token_expires = time.time() + max(int(payload.get("expires_in") or 3600) - 60, 30)
            return self._token
        if self._static_token:
            return self._static_token
        raise RuntimeError("spotify is not configured")

    def _throttle(self):
        gap = MIN_INTERVAL_SEC - (time.time() - self._last_call_at)
        if gap > 0:
            time.sleep(gap)
        self._last_call_at = time.time()

    def _get(self, path, params=None):
        wait = self._blocked_until - time.time()
        if wait > 0:
            raise SpotifyRateLimit(int(wait) + 1, "cached_block")
        self._throttle()
        url = f"{API_BASE}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        try:
            return _http_json(
                url,
                headers={"Authorization": f"Bearer {self._access_token()}"},
            )
        except SpotifyRateLimit as exc:
            self._blocked_until = time.time() + max(exc.retry_after, 1)
            raise

    def artist_popularity(self, query):
        query = (query or "").strip()
        if not query or not self.enabled:
            return 0
        try:
            search = self._get("/search", {
                "q": query,
                "type": "artist",
                "limit": 5,
            })
        except SpotifyRateLimit:
            return 0
        except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            logger.warning("spotify popularity failed for %s: %s", query, exc)
            return 0
        wanted = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
        best = 0
        for artist in ((search.get("artists") or {}).get("items") or []):
            name = re.sub(r"[^a-z0-9]+", " ", (artist.get("name") or "").lower()).strip()
            if not name:
                continue
            if name != wanted and wanted not in name and name not in wanted:
                if SequenceMatcher(None, wanted, name).ratio() < 0.86:
                    continue
            try:
                popularity = int(artist.get("popularity") or 0)
            except (TypeError, ValueError):
                popularity = 0
            if popularity > best:
                best = popularity
        return best

    def artist_snapshot(self, query, spotify_id=None):
        query = (query or "").strip()
        if not self.enabled:
            return {"error": "spotify_not_configured"}
        if not query and not spotify_id:
            return {"error": "empty_query"}
        # Search only. GET /artists/{id} has a harsher 429 window in Dev Mode.
        try:
            search = self._get("/search", {
                "q": query or spotify_id,
                "type": "artist",
                "limit": 5,
            })
            artist = _pick_search_artist(query or "", (search.get("artists") or {}).get("items") or [])
            if not artist and query:
                items = (search.get("artists") or {}).get("items") or []
                artist = items[0] if items else None
            if not artist:
                return {"spotify_id": None, "unmatched": True, "popularity": 0, "followers": 0}
            followers = ((artist.get("followers") or {}).get("total")) or 0
            try:
                popularity = int(artist.get("popularity") or 0)
            except (TypeError, ValueError):
                popularity = 0
            try:
                followers = int(followers or 0)
            except (TypeError, ValueError):
                followers = 0
            return {
                "spotify_id": artist.get("id"),
                "display_name": artist.get("name") or query,
                "popularity": popularity,
                "followers": followers,
            }
        except SpotifyRateLimit:
            raise
        except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            logger.warning("spotify snapshot failed for %s: %s", query or spotify_id, exc)
            return {"error": str(exc)}

    def lookup_artist(self, query, market="US"):
        query = (query or "").strip()
        if not query:
            return {"error": "missing_artist"}
        if not self.enabled:
            return {"error": "spotify_not_configured"}
        try:
            search = self._get("/search", {
                "q": query,
                "type": "artist,track",
                "limit": 5,
                "market": market,
            })
            artist = ((search.get("artists") or {}).get("items") or [None])[0]
            if not artist:
                return {"error": "not_found", "q": query}
            tracks = self._tracks_for_artist(artist, search.get("tracks") or {})
            genres = [genre for genre in (artist.get("genres") or [])[:3] if genre]
            url = ((artist.get("external_urls") or {}).get("spotify") or "").replace("https://", "")
            followers = ((artist.get("followers") or {}).get("total")) or 0
            card = {
                "name": artist.get("name") or query,
                "genres": genres,
                "followers": followers,
                "url": url,
                "tracks": tracks,
            }
            card["sms"] = self._format_sms(card)
            return card
        except SpotifyRateLimit as exc:
            logger.warning("spotify lookup rate limited for %s: retry_after=%s", query, exc.retry_after)
            return {"error": "rate_limited", "q": query}
        except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as exc:
            logger.warning("spotify lookup failed for %s: %s", query, exc)
            return {"error": "lookup_failed", "q": query}

    def _tracks_for_artist(self, artist, tracks_payload):
        artist_id = artist.get("id")
        artist_name = (artist.get("name") or "").strip().lower()
        chosen = []
        seen = set()
        ranked = []
        for track in tracks_payload.get("items") or []:
            names = [((person.get("name") or "").strip()) for person in (track.get("artists") or [])]
            ids = [person.get("id") for person in (track.get("artists") or [])]
            if artist_id and artist_id in ids:
                primary = ids[0] == artist_id
            elif artist_name and any(name.lower() == artist_name for name in names):
                primary = (names[0] or "").lower() == artist_name
            else:
                continue
            ranked.append((0 if primary else 1, track))
        ranked.sort(key=lambda item: item[0])
        for _, track in ranked:
            name = (track.get("name") or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            chosen.append({
                "name": name,
                "url": ((track.get("external_urls") or {}).get("spotify") or "").replace("https://", ""),
            })
            if len(chosen) >= 3:
                break
        return chosen

    def _format_sms(self, card):
        name = card.get("name") or "Artist"
        tracks = [f'"{item["name"]}"' for item in (card.get("tracks") or [])[:2] if item.get("name")]
        genre = (card.get("genres") or [None])[0]
        bits = [name]
        if genre:
            bits.append(genre)
        line = " · ".join(bits)
        if tracks:
            line = f"{line}: {', '.join(tracks)}"
        lines = [f"Listen: {line}"]
        if card.get("url"):
            lines.append(card["url"])
        return "\n".join(lines)


def _norm_artist_name(value):
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _pick_search_artist(query, items):
    wanted = _norm_artist_name(query)
    if not wanted:
        return None
    ranked = []
    for artist in items or []:
        name = _norm_artist_name(artist.get("name"))
        if not name:
            continue
        if name == wanted:
            return artist
        if wanted in name or name in wanted:
            ratio = 0.92
        else:
            ratio = SequenceMatcher(None, wanted, name).ratio()
        if ratio >= 0.86:
            ranked.append((ratio, artist))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def parse_stored_headliners(value, limit=3):
    """Read headliner storage: JSON list, comma-separated text, or a single name."""
    try:
        from services.catalog_normalize import parse_headliners
    except ImportError:
        try:
            from catalog_normalize import parse_headliners
        except ImportError:
            parse_headliners = None
    if parse_headliners:
        return parse_headliners(value, limit=limit)
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw_parts = list(value)
    else:
        text = str(value).strip()
        if not text or text.lower() in {"null", "none", "n/a", "tba", "tbd", "unknown"}:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, list):
                raw_parts = parsed
            else:
                raw_parts = [text]
        else:
            raw_parts = re.split(r"\s*,\s*", text)

    artists = []
    seen = set()
    for part in raw_parts:
        cleaned = " ".join(str(part or "").split()).strip(" -|/")
        if not cleaned or cleaned.lower() in GENERIC_HEADLINERS:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        artists.append(cleaned)
        if len(artists) >= limit:
            break
    return artists


def serialize_headliners(artists, limit=3):
    """Persist artists as a JSON list string for the headliner column."""
    try:
        from services.catalog_normalize import serialize_headliners as _ser
        return _ser(artists, limit=limit)
    except ImportError:
        try:
            from catalog_normalize import serialize_headliners as _ser
            return _ser(artists, limit=limit)
        except ImportError:
            pass
    parts = parse_stored_headliners(artists, limit=limit)
    if not parts:
        return ""
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def headliners_from_event_name(event_name, limit=3):
    name = (event_name or "").strip()
    if not name:
        return []
    split = re_split_headliner(name)
    artists = []
    for part in split:
        cleaned = " ".join(part.split()).strip(" -|/")
        cleaned = re.split(r"\s+-\s+", cleaned, maxsplit=1)[0].strip(" -|/")
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in GENERIC_HEADLINERS or len(cleaned) < 2:
            continue
        if cleaned not in artists:
            artists.append(cleaned)
        if len(artists) >= limit:
            break
    if not artists and len(name) <= 28 and name.lower() not in GENERIC_HEADLINERS:
        artists = [name]
    return artists


def headliners_for_event(event, limit=3):
    """Prefer scrape-time `headliner` list; also parse event_name for gaps.

    Storage is a JSON list string (legacy: comma-separated or single name).
    """
    if not isinstance(event, dict):
        return headliners_from_event_name(event or "", limit=limit)

    parts = []
    seen = set()

    def _add(name):
        cleaned = " ".join(str(name or "").split()).strip(" -|/")
        if not cleaned or cleaned.lower() in GENERIC_HEADLINERS:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        parts.append(cleaned)

    for name in parse_stored_headliners(event.get("headliner"), limit=limit):
        _add(name)
        if len(parts) >= limit:
            return parts[:limit]

    for name in headliners_from_event_name(event.get("event_name") or "", limit=limit):
        _add(name)
        if len(parts) >= limit:
            break
    return parts[:limit]


def re_split_headliner(name):
    """Split a title into billed acts. Keep both sides of w/with/ft/presents."""
    lowered = (name or "").strip()
    # Festival/brand prefix: "Title: Artist A, Artist B" (colon + space).
    # Do not split artist punctuation like Blond:ish or BUNT.
    if re.search(r":\s+\S", lowered):
        after = lowered.split(":", 1)[1].strip()
        if after:
            lowered = after
    parts = re.split(
        r"\s+(?:w/|with|ft\.?|feat\.?|featuring|presents|b2b)\s+|\s*,\s*|\s+[&+/|]\s+",
        lowered,
        flags=re.I,
    )
    return [re.sub(r"\s*\([^)]*\)\s*", " ", part).strip() for part in parts if part.strip()]
