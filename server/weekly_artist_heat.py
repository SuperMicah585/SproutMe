#!/usr/bin/env python3.10
"""Monday Pacific weekly ListenBrainz heat refresh for rise / hot scores.

PythonAnywhere only schedules daily/hourly, so this exits early on other days.
Does not scrape or wipe Events_table.
"""
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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


def main():
    now = datetime.now(ZoneInfo("America/Los_Angeles"))
    if now.weekday() != 0:
        print(f"Skipping weekly artist heat ({now.strftime('%A %Y-%m-%d %Z')}).")
        return 0

    _load_local_env()

    try:
        from supabase import create_client
    except ImportError:
        sys.modules.pop("supabase", None)
        sys.path = [p for p in sys.path if Path(p).resolve() != HERE]
        from supabase import create_client
        if str(HERE) not in sys.path:
            sys.path.insert(0, str(HERE))

    from services.artist_heat import refresh_artist_heat_cache, unique_headliners

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("SUPABASE_URL and SUPABASE_KEY are required.")
        return 1

    client = create_client(url, key)
    records = []
    start = 0
    page = 1000
    while True:
        chunk = (
            client.table("Events_table")
            .select("event_name")
            .range(start, start + page - 1)
            .execute()
            .data
            or []
        )
        records.extend(chunk)
        if len(chunk) < page:
            break
        start += page

    names = unique_headliners(records)
    print(
        f"Weekly artist heat (ListenBrainz) at {now.isoformat()}: "
        f"{len(records)} events, {len(names)} headliners."
    )
    stats = refresh_artist_heat_cache(
        client,
        records,
        max_fetch=None,
        weekly=True,
    )
    print(
        "Weekly artist heat done: "
        f"{stats.get('fetched', 0)} fetched, "
        f"{stats.get('hits', 0)} already cached, "
        f"{stats.get('unmatched', 0)} unmatched, "
        f"{stats.get('snapshots', 0)} snapshots, "
        f"{stats.get('errors', 0)} errors."
    )
    return 0 if not stats.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
