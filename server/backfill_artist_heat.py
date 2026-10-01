#!/usr/bin/env python3.10
"""Backfill artist_heat_cache from Events_table. Does not scrape or wipe events."""
import os
import sys
from pathlib import Path

try:
    from supabase import create_client
except ImportError:
    sys.modules.pop("supabase", None)
    _here = Path(__file__).resolve().parent if "__file__" in globals() else None
    if _here:
        sys.path = [p for p in sys.path if Path(p).resolve() != _here]
    from supabase import create_client

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def _load_local_env():
    roots = [
        HERE / ".env",
        HERE.parent / ".env",
        Path("/home/phelpsm4/sproutMe/.env"),
        Path("/home/phelpsm4/sproutMe/spotify.env"),
    ]
    for path in roots:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and not os.environ.get(key):
                os.environ[key] = value


_load_local_env()

from services.artist_heat import refresh_artist_heat_cache, unique_headliners


def _fetch_event_names(client, table_name="Events_table"):
    records = []
    start = 0
    page = 1000
    while True:
        response = (
            client.table(table_name)
            .select("event_name")
            .range(start, start + page - 1)
            .execute()
        )
        chunk = response.data or []
        records.extend(chunk)
        if len(chunk) < page:
            break
        start += page
    return records


def main():
    args = [arg for arg in sys.argv[1:] if arg != "--"]
    limit = None
    weekly = False
    extra = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--weekly":
            weekly = True
            index += 1
            continue
        if arg == "--limit" and index + 1 < len(args):
            limit = int(args[index + 1])
            index += 2
            continue
        extra.append(arg)
        index += 1
    if extra:
        print("Usage: backfill_artist_heat.py [--weekly] [--limit 80]")
        return 2

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_KEY are required.")
        return 1

    client = create_client(url, key)
    records = _fetch_event_names(client)
    if not records:
        print("No events in Events_table. Run the scrape first.")
        return 1

    names = unique_headliners(records)
    eta_min = max(len(names) * 1.2 / 60.0, 0.1)
    print(
        f"Events_table rows: {len(records)}. Unique headliners: {len(names)}. "
        f"MusicBrainz/ListenBrainz paced at 1.2s; full unseen fill ~{eta_min:.0f} min if cache is empty."
    )
    stats = refresh_artist_heat_cache(
        client,
        records,
        max_fetch=limit,
        weekly=weekly,
    )
    print(
        "Artist heat backfill done: "
        f"{stats.get('fetched', 0)} fetched, "
        f"{stats.get('hits', 0)} already cached, "
        f"{stats.get('unmatched', 0)} unmatched, "
        f"{stats.get('snapshots', 0)} snapshots, "
        f"{stats.get('errors', 0)} errors, "
        f"{stats.get('deferred', 0)} deferred."
    )
    return 0 if not stats.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
