"""Sticky SMS session slots — source of truth for city/genre/date across turns."""
from __future__ import annotations

import json
import re
from copy import deepcopy

SLOT_KEYS = (
    "city",
    "genre",
    "date_phrase",
    "artist",
    "venue",
    "origin",
    "transit_intent",
    "neighborhood",
    "active_ask",
    "last_show_ids",
    "last_cards",
    "compare_to",
)

SLOTS_ROLE = "_slots"

OUT_OF_SCOPE_RE = re.compile(
    r"\b(strip\s*clubs?|gentleman'?s?\s+clubs?|escorts?|prostitut|"
    r"hookers?|onlyfans|casino\s+cheat|how\s+to\s+make\s+drugs)\b",
    re.I,
)

COMPARE_RE = re.compile(
    r"\b(compare|vs\.?|versus|how\s+does\s+.+\s+compare|compared\s+to)\b",
    re.I,
)
DETAILS_RE = re.compile(
    r"\b(details?|tell\s+me\s+more|more\s+(info|about)|what'?s\s+it\s+like|"
    r"lineup|who'?s\s+(playing|on)|who\s+plays|main\s+artists?)\b",
    re.I,
)
PLAN_RE = re.compile(
    r"\b(where\s+should\s+i|help\s+me\s+(pick|choose|find)|plan\s+(my\s+)?night|"
    r"what\s+should\s+i\s+(go\s+to|see|do)|recommend|best\s+(show|night|option))\b",
    re.I,
)
ENTITY_WHO_RE = re.compile(
    r"\b(who\s+is|what\s+kind\s+of\s+music|what\s+genre|are\s+they)\b",
    re.I,
)
ARTIST_SHOW_RE = re.compile(
    r"\b(.+?)\s+(show|concert|gig|tour|playing|comes?\s+to|in)\b",
    re.I,
)
TRANSIT_RE = re.compile(
    r"\b(light\s*rail|link|max|transit|no\s+car|without\s+a\s+car|won'?t\s+have\s+a\s+car|"
    r"car[- ]?free|walkable|stations?)\b",
    re.I,
)
SECOND_ONE_RE = re.compile(r"\b(the\s+)?(second|2nd|first|1st|third|3rd)\s+(one|show|option)\b", re.I)


def empty_slots():
    return {
        "city": None,
        "genre": None,
        "date_phrase": None,
        "artist": None,
        "venue": None,
        "origin": None,
        "transit_intent": False,
        "neighborhood": None,
        "active_ask": None,
        "last_show_ids": [],
        "last_cards": [],
        "compare_to": None,
    }


def load_slots_from_messages(messages):
    """Pull sticky slots from a `_slots` message embedded in the conversation."""
    for item in reversed(messages or []):
        if item.get("role") != SLOTS_ROLE:
            continue
        raw = item.get("content") or ""
        try:
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (TypeError, json.JSONDecodeError):
            data = {}
        if isinstance(data, dict):
            base = empty_slots()
            base.update({k: data.get(k) for k in SLOT_KEYS if k in data})
            base["transit_intent"] = bool(base.get("transit_intent"))
            base["last_show_ids"] = list(base.get("last_show_ids") or [])
            base["last_cards"] = list(base.get("last_cards") or [])
            return base
    return empty_slots()


def upsert_slots_message(messages, slots):
    """Replace or append the `_slots` record; filter these out of model history."""
    payload = {k: deepcopy(slots.get(k)) for k in SLOT_KEYS}
    cleaned = [m for m in (messages or []) if m.get("role") != SLOTS_ROLE]
    cleaned.append({"role": SLOTS_ROLE, "content": json.dumps(payload, default=str)})
    return cleaned


def filter_public_messages(messages):
    return [m for m in (messages or []) if m.get("role") != SLOTS_ROLE]


def clear_topic_slots(slots):
    """Hard topic reset — keep nothing from prior ask except empty shell."""
    return empty_slots()


def merge_evidence_into_slots(slots, evidence):
    """After a successful retrieval, remember cards for follow-ups."""
    out = deepcopy(slots or empty_slots())
    shows = (evidence or {}).get("shows") or []
    cards = (evidence or {}).get("cards") or []
    out["last_show_ids"] = [
        str(s.get("id")) for s in shows if s.get("id") is not None
    ][:5]
    out["last_cards"] = list(cards)[:5]
    applied = (evidence or {}).get("applied") or {}
    if applied.get("city"):
        out["city"] = applied["city"]
    if applied.get("genre"):
        out["genre"] = applied["genre"]
    if applied.get("date_phrase"):
        out["date_phrase"] = applied["date_phrase"]
    if applied.get("artist"):
        out["artist"] = applied["artist"]
    if applied.get("origin"):
        out["origin"] = applied["origin"]
    return out
