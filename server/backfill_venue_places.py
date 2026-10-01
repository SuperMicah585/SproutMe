#!/usr/bin/env python3.10
"""Backfill venue_place_cache from Events_table. Does not scrape or wipe events."""
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
        Path("/home/phelpsm4/sproutMe/places.env"),
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

from services.venue_places import refresh_venue_place_cache, unique_venues


def _fetch_event_venues(client, table_name="Events_table"):
    records = []
    start = 0
    page = 1000
    while True:
        response = (
            client.table(table_name)
            .select("venue,city")
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
    city = None
    extra = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--limit" and index + 1 < len(args):
            limit = int(args[index + 1])
            index += 2
            continue
        if arg == "--city" and index + 1 < len(args):
            city = args[index + 1].strip()
            index += 2
            continue
        extra.append(arg)
        index += 1
    if extra:
        print("Usage: backfill_venue_places.py [--city Seattle] [--limit 50]")
        return 2

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_KEY are required.")
        return 1
    if not (os.environ.get("GOOGLE_PLACES_API_KEY") or "").strip():
        print("GOOGLE_PLACES_API_KEY is not set.")
        return 1

    client = create_client(url, key)
    records = _fetch_event_venues(client)
    if city:
        needle = city.lower()
        records = [
            rec for rec in records
            if needle in (rec.get("city") or "").lower()
            or needle in (rec.get("venue") or "").lower()
        ]
    if not records:
        print("No events in Events_table. Run the scrape first.")
        return 1

    rooms = unique_venues(records)
    print(f"Events_table rows: {len(records)}. Usable unique rooms: {len(rooms)}.")
    stats = refresh_venue_place_cache(
        client,
        records,
        ttl_days=180,
        max_fetch=limit,
    )
    print(
        "Backfill done: "
        f"{stats.get('fetched', 0)} fetched, "
        f"{stats.get('hits', 0)} already cached, "
        f"{stats.get('unmatched', 0)} unmatched, "
        f"{stats.get('errors', 0)} errors, "
        f"{stats.get('deferred', 0)} deferred."
    )
    return 0 if not stats.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
