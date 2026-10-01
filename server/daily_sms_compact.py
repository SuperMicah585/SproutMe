#!/usr/bin/env python3
"""Daily 7am Pacific SMS memory compact: fold older turns into global_rules, trim window.

Schedule on PythonAnywhere / Railway cron around 7:00 America/Los_Angeles.
Safe to call once per day; skips threads with little history.
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
    # Allow forced runs; default skip unless hour is 7 (PA may fire nearby).
    force = os.environ.get("SMS_COMPACT_FORCE", "").lower() in {"1", "true", "yes"}
    if not force and now.hour != 7:
        print(f"Skipping SMS compact at {now.strftime('%Y-%m-%d %H:%M %Z')} (want 7am Pacific).")
        return 0

    _load_local_env()

    from flask_app import sms_agent

    stats = sms_agent.compact_conversations()
    print(f"SMS compact @ {now.isoformat()}: {stats}")
    return 0 if stats.get("errors", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
