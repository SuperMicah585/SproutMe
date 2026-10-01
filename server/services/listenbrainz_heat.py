"""MusicBrainz + ListenBrainz artist heat. Spotify is not used here."""
import json
import logging
import math
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

USER_AGENT = "SproutMe/1.0 (https://sproutme-please.com; micahphlps@gmail.com)"
MB_SEARCH_URL = "https://musicbrainz.org/ws/2/artist/"
LB_POPULARITY_URL = "https://api.listenbrainz.org/1/popularity/artist"
MB_MIN_INTERVAL_SEC = 1.2
LB_MIN_INTERVAL_SEC = 1.2
LB_BATCH_SIZE = 50
LISTEN_POP_CAP = 10_000_000
TIMEOUT_SEC = 20


class HeatRateLimit(Exception):
    def __init__(self, retry_after=30, source="listenbrainz"):
        try:
            self.retry_after = max(int(retry_after or 30), 1)
        except (TypeError, ValueError):
            self.retry_after = 30
        self.source = source
        super().__init__(f"{source} rate limited retry_after={self.retry_after}s")


def _clean(value):
    return " ".join(str(value or "").split()).strip()


def listens_to_popularity(listen_count):
    try:
        listens = max(int(listen_count or 0), 0)
    except (TypeError, ValueError):
        return 0
    if listens <= 0:
        return 0
    ratio = math.log1p(listens) / math.log1p(LISTEN_POP_CAP)
    return int(round(min(max(ratio, 0.0), 1.0) * 100))


class CatalogHeat:
    def __init__(self):
        self._mb_last_at = 0.0
        self._lb_last_at = 0.0

    def _pace(self, last_at, minimum):
        gap = minimum - (time.time() - last_at)
        if gap > 0:
            time.sleep(gap)
        return time.time()

    def _request(self, url, *, data=None, source="catalog"):
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        last_error = None
        for attempt in range(2):
            req = Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
            try:
                with urlopen(req, timeout=TIMEOUT_SEC) as resp:
                    reset_in = resp.headers.get("X-RateLimit-Reset-In")
                    remaining = resp.headers.get("X-RateLimit-Remaining")
                    raw = resp.read().decode("utf-8", "replace")
                payload = json.loads(raw) if raw else {}
                try:
                    if remaining is not None and int(remaining) <= 0 and reset_in:
                        time.sleep(max(int(reset_in), 1))
                except (TypeError, ValueError):
                    pass
                return payload
            except HTTPError as exc:
                retry = exc.headers.get("Retry-After") or exc.headers.get("X-RateLimit-Reset-In") or "30"
                if exc.code in (429, 503):
                    raise HeatRateLimit(retry, source) from exc
                body = exc.read().decode("utf-8", "replace")
                raise RuntimeError(f"{source} HTTP {exc.code}: {body[:180]}") from exc
            except (URLError, TimeoutError) as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise RuntimeError(f"{source} request failed: {exc}") from exc
        raise RuntimeError(f"{source} request failed: {last_error}")

    def lookup_mbid(self, query):
        needle = _clean(query)
        if len(needle) < 2:
            return None
        self._mb_last_at = self._pace(self._mb_last_at, MB_MIN_INTERVAL_SEC)
        safe = needle.replace('"', "")
        params = urlencode({
            "query": f'artist:"{safe}" OR alias:"{safe}" OR {safe}',
            "fmt": "json",
            "limit": 5,
        })
        try:
            payload = self._request(f"{MB_SEARCH_URL}?{params}", source="musicbrainz")
        except HeatRateLimit:
            raise
        except Exception as exc:
            logger.warning("musicbrainz lookup failed for %s: %s", needle, exc)
            return None
        artist = _pick_mb_artist(needle, payload.get("artists") or [])
        if not artist:
            return None
        return {
            "mbid": artist.get("id"),
            "display_name": artist.get("name") or needle,
        }

    def popularity_for_mbids(self, mbids):
        wanted = []
        seen = set()
        for mbid in mbids or []:
            mbid = (mbid or "").strip()
            if not mbid or mbid in seen:
                continue
            seen.add(mbid)
            wanted.append(mbid)
        out = {}
        for start in range(0, len(wanted), LB_BATCH_SIZE):
            chunk = wanted[start:start + LB_BATCH_SIZE]
            self._lb_last_at = self._pace(self._lb_last_at, LB_MIN_INTERVAL_SEC)
            body = json.dumps({"artist_mbids": chunk}).encode()
            payload = self._request(LB_POPULARITY_URL, data=body, source="listenbrainz")
            rows = payload if isinstance(payload, list) else []
            for row in rows:
                mbid = row.get("artist_mbid")
                if not mbid:
                    continue
                listens = row.get("total_listen_count")
                users = row.get("total_user_count")
                if listens is None and users is None:
                    continue
                out[mbid] = {
                    "listen_count": int(listens or 0),
                    "listener_count": int(users or 0),
                    "popularity": listens_to_popularity(listens or 0),
                }
        return out


def _pick_mb_artist(query, items):
    wanted = _clean(query).lower()
    if not wanted or not items:
        return None
    wanted_fold = _fold(wanted)
    exact = []
    keyed = []
    for artist in items:
        try:
            score = int(artist.get("score") or 0)
        except (TypeError, ValueError):
            score = 0
        names = _artist_names(artist)
        if not names:
            continue
        lowered = [name.lower() for name in names]
        if wanted in lowered:
            exact.append((score, artist))
            continue
        if any(_fold(name) == wanted_fold for name in lowered) and score >= 75:
            keyed.append((score, artist))
    pool = exact or keyed
    if not pool:
        return None
    pool.sort(key=lambda item: item[0], reverse=True)
    return pool[0][1]


def _artist_names(artist):
    names = [_clean(artist.get("name"))]
    for alias in artist.get("aliases") or []:
        if isinstance(alias, dict):
            names.append(_clean(alias.get("name")))
        else:
            names.append(_clean(alias))
    return [name for name in names if name]


def _compact(value):
    return "".join(ch for ch in (value or "") if ch.isalnum() or ch in ".-").lower()


def _fold(value):
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _compact(text)
