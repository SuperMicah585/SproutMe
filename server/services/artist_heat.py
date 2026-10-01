import logging
import math
import re
import time
from datetime import datetime, timezone

from services.spotify_service import headliners_for_event
from services.listenbrainz_heat import CatalogHeat, HeatRateLimit

logger = logging.getLogger(__name__)

CACHE_TABLE = "artist_heat_cache"
SNAPSHOT_TABLE = "artist_heat_snapshots"
MAX_FETCH_PER_RUN = 80
FETCH_PAUSE_SEC = 0.2
MAX_RETRY_AFTER_SEC = 180
LB_FLUSH_SIZE = 50
JUNK_HEADLINER_RE = re.compile(
    r"\b(festival|fest\b|campout|camp out|day party|night party|rave experience)\b",
    re.I,
)
BREAKOUT_MIN_POP = 40
BREAKOUT_MAX_FOLLOWERS = 80000
SLOPE_WEEKS = 8


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def artist_key(name):
    text = _clean(name).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def unique_headliners(records, per_event=3):
    seen = {}
    for rec in records or []:
        for name in headliners_for_event(rec, limit=per_event):
            key = artist_key(name)
            if not key or len(name) > 48:
                continue
            if JUNK_HEADLINER_RE.search(name):
                continue
            if re.search(r"\b20\d{2}\b", name) and not re.search(r"\btour\b", name, re.I):
                continue
            if key in seen:
                continue
            seen[key] = {"artist_key": key, "query": name}
    return list(seen.values())


def breakout_score(popularity, followers):
    try:
        pop = int(popularity or 0)
    except (TypeError, ValueError):
        pop = 0
    try:
        fans = int(followers or 0)
    except (TypeError, ValueError):
        fans = 0
    if pop < BREAKOUT_MIN_POP or fans >= BREAKOUT_MAX_FOLLOWERS:
        return 0.0
    return pop / math.log(fans + 2)


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


def _pages(supabase, table, columns="*"):
    rows = []
    start = 0
    page = 1000
    while True:
        response = supabase.table(table).select(columns).range(start, start + page - 1).execute()
        chunk = response.data or []
        rows.extend(chunk)
        if len(chunk) < page:
            break
        start += page
    return rows


def load_heat_index(rows):
    by_key = {}
    for row in rows or []:
        key = artist_key(row.get("artist_key") or "")
        name = artist_key(row.get("display_name") or row.get("query") or "")
        if key:
            by_key[key] = row
        if name:
            by_key[name] = row
    return by_key


def match_heat(index, name):
    if not index:
        return None
    key = artist_key(name)
    if not key:
        return None
    return index.get(key)


def heat_popularity(row):
    if isinstance(row, dict):
        try:
            return int(row.get("popularity") or 0)
        except (TypeError, ValueError):
            return 0
    try:
        return int(row or 0)
    except (TypeError, ValueError):
        return 0


def heat_breakout(row):
    if not isinstance(row, dict):
        return 0.0
    try:
        rise = float(row.get("rise_score") or 0)
    except (TypeError, ValueError):
        rise = 0.0
    return max(breakout_score(row.get("popularity"), row.get("followers")), rise)


def _upsert(supabase, table, rows, chunk_size=50):
    errors = 0
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        try:
            supabase.table(table).upsert(chunk).execute()
        except Exception as exc:
            errors += len(chunk)
            print(f"{table} save failed: {exc}")
    return errors


def _insert(supabase, table, rows, chunk_size=50):
    errors = 0
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        try:
            supabase.table(table).insert(chunk).execute()
        except Exception as exc:
            errors += len(chunk)
            print(f"{table} insert failed: {exc}")
    return errors


def _snapshot_map(supabase, keys):
    wanted = set(keys)
    grouped = {key: [] for key in wanted}
    if not wanted:
        return grouped
    rows = _pages(supabase, SNAPSHOT_TABLE, "artist_key,popularity,followers,fetched_at")
    for row in rows:
        key = row.get("artist_key")
        if key not in wanted:
            continue
        grouped[key].append(row)
    for key, items in grouped.items():
        items.sort(key=lambda item: _parse_fetched_at(item.get("fetched_at")) or datetime.min.replace(tzinfo=timezone.utc))
        grouped[key] = items[-SLOPE_WEEKS:]
    return grouped


def rise_score_from_snapshots(points, followers=None):
    if not points or len(points) < 2:
        return 0.0
    try:
        fans = int(followers if followers is not None else (points[-1].get("followers") or 0))
    except (TypeError, ValueError):
        fans = 0
    if fans >= BREAKOUT_MAX_FOLLOWERS:
        return 0.0
    first = points[0]
    last = points[-1]
    try:
        pop_delta = int(last.get("popularity") or 0) - int(first.get("popularity") or 0)
    except (TypeError, ValueError):
        pop_delta = 0
    try:
        start_fans = max(int(first.get("followers") or 0), 1)
        end_fans = int(last.get("followers") or 0)
        follower_pct = (end_fans - start_fans) / start_fans
    except (TypeError, ValueError):
        follower_pct = 0.0
    weeks_up = 0
    for left, right in zip(points, points[1:]):
        try:
            if int(right.get("popularity") or 0) > int(left.get("popularity") or 0):
                weeks_up += 1
            elif int(right.get("followers") or 0) > int(left.get("followers") or 0) * 1.05:
                weeks_up += 1
        except (TypeError, ValueError):
            continue
    if pop_delta <= 0 and follower_pct < 0.08:
        return 0.0
    return max(0.0, pop_delta + (10.0 * follower_pct) + weeks_up)


def _cache_has_mbid(supabase):
    try:
        supabase.table(CACHE_TABLE).select("mbid").limit(1).execute()
        return True
    except Exception as exc:
        logger.warning("artist_heat_cache.mbid unavailable: %s", exc)
        print("artist_heat_cache.mbid is missing; upserts will omit it. Run server/supabase/artist_heat.sql to add it.")
        return False


def _strip_mbid(rows):
    cleaned = []
    for row in rows:
        item = dict(row)
        item.pop("mbid", None)
        cleaned.append(item)
    return cleaned


def _heat_row(item, existing, stats, stamp, weekly, history):
    key = item.get("artist_key") or artist_key(item.get("query") or item.get("display_name") or "")
    mbid = item.get("mbid") or existing.get("mbid")
    popularity = stats.get("popularity")
    followers = stats.get("listener_count")
    row = {
        "artist_key": key,
        "query": item.get("query") or existing.get("query") or key,
        "spotify_id": existing.get("spotify_id"),
        "mbid": mbid,
        "display_name": item.get("display_name") or existing.get("display_name") or item.get("query") or key,
        "popularity": popularity,
        "followers": followers,
        "fetched_at": stamp,
        "updated_at": stamp,
    }
    if existing.get("fetched_at") and weekly:
        row["prev_popularity"] = existing.get("popularity")
        row["prev_followers"] = existing.get("followers")
        row["prev_fetched_at"] = existing.get("fetched_at")
    else:
        row["prev_popularity"] = existing.get("prev_popularity")
        row["prev_followers"] = existing.get("prev_followers")
        row["prev_fetched_at"] = existing.get("prev_fetched_at")
    points = list(history.get(key) or [])
    if weekly or not existing:
        points.append({
            "artist_key": key,
            "popularity": popularity,
            "followers": followers,
            "fetched_at": stamp,
        })
    row["rise_score"] = rise_score_from_snapshots(points, followers=followers)
    snapshot = {
        "artist_key": key,
        "spotify_id": existing.get("spotify_id"),
        "popularity": popularity,
        "followers": followers,
        "fetched_at": stamp,
    }
    return row, snapshot


def refresh_artist_heat_cache(
    supabase,
    records,
    spotify=None,
    max_fetch=MAX_FETCH_PER_RUN,
    weekly=False,
):
    artists = unique_headliners(records)
    if not artists:
        return {"artists": 0, "hits": 0, "fetched": 0, "errors": 0, "deferred": 0}
    if not supabase:
        return {"artists": len(artists), "hits": 0, "fetched": 0, "errors": 0, "deferred": 0, "skipped": True}

    cached_rows = _pages(supabase, CACHE_TABLE)
    cached = {row.get("artist_key"): row for row in cached_rows if row.get("artist_key")}
    missing = [item for item in artists if item["artist_key"] not in cached]
    if weekly:
        todo = list(cached.values())
        for item in missing:
            todo.append(item)
    else:
        todo = missing

    if max_fetch is None:
        deferred = 0
    else:
        deferred = max(0, len(todo) - max_fetch)
        todo = todo[:max_fetch]
    hits = len(artists) - len(missing)
    print(
        f"Artist heat plan: {len(artists)} headliners, {len(missing)} unseen, "
        f"{len(todo)} this run, {deferred} deferred, source=listenbrainz, weekly={weekly}."
    )

    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    fetched = 0
    errors = 0
    unmatched = 0
    rows = []
    snapshots = []
    snapshot_count = 0
    snapshot_keys = [item.get("artist_key") for item in todo if item.get("artist_key")]
    history = _snapshot_map(supabase, snapshot_keys) if weekly else {}
    catalog = CatalogHeat()
    pending = []
    stopped = False
    include_mbid = _cache_has_mbid(supabase)

    def flush():
        nonlocal rows, snapshots, errors, snapshot_count
        if not rows and not snapshots:
            return
        payload = rows if include_mbid else _strip_mbid(rows)
        errors += _upsert(supabase, CACHE_TABLE, payload)
        errors += _insert(supabase, SNAPSHOT_TABLE, snapshots)
        snapshot_count += len(snapshots)
        rows = []
        snapshots = []

    def flush_pending():
        nonlocal pending, fetched, unmatched, stopped, errors
        if not pending:
            return
        mbids = [item["mbid"] for item in pending if item.get("mbid")]
        try:
            stats_by_mbid = catalog.popularity_for_mbids(mbids)
        except HeatRateLimit as exc:
            if exc.retry_after > MAX_RETRY_AFTER_SEC:
                print(f"Stopping ListenBrainz heat: retry_after={exc.retry_after}s")
                stopped = True
                pending = []
                return
            print(f"ListenBrainz 429; waiting {exc.retry_after}s, then one retry.")
            time.sleep(exc.retry_after + 1)
            try:
                stats_by_mbid = catalog.popularity_for_mbids(mbids)
            except HeatRateLimit as exc2:
                print(f"Still 429 after Retry-After; stopping. retry_after={exc2.retry_after}s")
                stopped = True
                pending = []
                return
        except Exception as exc:
            logger.warning("listenbrainz batch failed: %s", exc)
            print(f"ListenBrainz batch failed ({exc}); waiting 2s and retrying once.")
            time.sleep(2)
            try:
                stats_by_mbid = catalog.popularity_for_mbids(mbids)
            except Exception as exc2:
                logger.warning("listenbrainz batch retry failed: %s", exc2)
                errors += 1
                pending = []
                return
        for item in pending:
            key = item.get("artist_key")
            existing = cached.get(key) or {}
            stats = stats_by_mbid.get(item.get("mbid"))
            if not stats:
                unmatched += 1
                continue
            row, snapshot = _heat_row(item, existing, stats, stamp, weekly, history)
            rows.append(row)
            if weekly or not existing:
                snapshots.append(snapshot)
            fetched += 1
        pending = []
        flush()

    for index, item in enumerate(todo):
        key = item.get("artist_key") or artist_key(item.get("query") or item.get("display_name") or "")
        existing = cached.get(key) or {}
        mbid = item.get("mbid") or existing.get("mbid")
        display_name = item.get("display_name") or existing.get("display_name")
        if not mbid:
            try:
                match = catalog.lookup_mbid(item.get("query") or display_name or key)
            except HeatRateLimit as exc:
                flush_pending()
                if exc.retry_after > MAX_RETRY_AFTER_SEC:
                    print(f"Stopping MusicBrainz heat: retry_after={exc.retry_after}s")
                    stopped = True
                    break
                print(f"MusicBrainz 429/503; waiting {exc.retry_after}s, then one retry.")
                time.sleep(exc.retry_after + 1)
                try:
                    match = catalog.lookup_mbid(item.get("query") or display_name or key)
                except HeatRateLimit as exc2:
                    print(f"Still rate limited; stopping. retry_after={exc2.retry_after}s")
                    stopped = True
                    break
            if not match or not match.get("mbid"):
                unmatched += 1
                if (index + 1) % 25 == 0 or index + 1 == len(todo):
                    print(f"Artist heat resolved {index + 1}/{len(todo)} (unmatched {unmatched}).")
                continue
            mbid = match["mbid"]
            display_name = match.get("display_name") or display_name
        pending.append({
            "artist_key": key,
            "query": item.get("query") or existing.get("query") or key,
            "display_name": display_name,
            "mbid": mbid,
        })
        if len(pending) >= LB_FLUSH_SIZE:
            flush_pending()
            if stopped:
                break
        if (index + 1) % 25 == 0 or index + 1 == len(todo):
            print(f"Artist heat resolved {index + 1}/{len(todo)} (unmatched {unmatched}).")

    if not stopped:
        flush_pending()
    flush()
    print(
        f"Artist heat cache: {len(artists)} headliners, {hits} already cached, "
        f"{fetched} fetched, {unmatched} unmatched, {deferred} deferred, "
        f"{errors} errors{' (stopped on rate limit)' if stopped else ''}."
    )
    return {
        "artists": len(artists),
        "hits": hits,
        "fetched": fetched,
        "unmatched": unmatched,
        "deferred": deferred,
        "errors": errors,
        "snapshots": snapshot_count,
    }
