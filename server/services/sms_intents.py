"""Intent classification + retrieval-first handlers for SproutMe SMS."""
from __future__ import annotations

import logging
import re
from copy import deepcopy

from services.sms_session import (
    COMPARE_RE,
    DETAILS_RE,
    ENTITY_WHO_RE,
    OUT_OF_SCOPE_RE,
    PLAN_RE,
    SECOND_ONE_RE,
    TRANSIT_RE,
    empty_slots,
)

logger = logging.getLogger(__name__)

INTENTS = (
    "out_of_scope",
    "find_artist",
    "find_shows",
    "refine",
    "entity_info",
    "plan_night",
    "meta",
)

STOP_FILLER = {
    "show", "shows", "concert", "gig", "tour", "event", "events", "tickets",
    "playing", "please", "any", "the", "a", "an", "me", "my", "in", "at", "to",
    "for", "on", "of", "and", "or", "what", "when", "where", "which", "who",
    "is", "are", "do", "does", "can", "you", "find", "looking", "want", "wanna",
    "coming", "up", "this", "next", "weekend", "tonight", "today", "tomorrow",
    "saturday", "sunday", "friday", "options", "recommend", "recommendation",
    "details", "detail", "info", "more", "about", "like", "it", "its", "it's",
}

GENRE_WORD_RE = re.compile(
    r"\b(house|techno|bass|trance|dubstep|garage|hardstyle|edm|drum\s*and\s*bass|dnb)\b",
    re.I,
)


def classify_intent(text, slots=None, history=None):
    """Rule-first intent. LLM is not required."""
    raw = (text or "").strip()
    lowered = raw.lower()
    slots = slots or empty_slots()

    if OUT_OF_SCOPE_RE.search(raw):
        return "out_of_scope"

    # Date-only refine while an artist ask is active — not a new genre browse
    if (
        slots.get("artist")
        and re.search(
            r"\b(in\s+\d+\s+days?|tonight|tomorrow|this weekend|next weekend)\b",
            lowered,
        )
        and len(raw.split()) <= 8
        and not GENRE_WORD_RE.search(raw)
        and not COMPARE_RE.search(raw)
    ):
        return "find_artist"

    if SECOND_ONE_RE.search(raw) and (slots.get("last_cards") or slots.get("last_show_ids")):
        return "refine"

    if COMPARE_RE.search(raw) and (slots.get("last_cards") or slots.get("genre") or slots.get("city")):
        return "refine"

    if DETAILS_RE.search(raw):
        if re.search(r"\b(lineup|who'?s\s+(playing|on)|who\s+plays|main\s+artists?)\b", lowered):
            return "entity_info"
        # "reload details" / "more details" — never invent vibes
        return "refine"

    if ENTITY_WHO_RE.search(raw):
        return "entity_info"

    # Genre + city/date show browse beats a leftover artist slot
    if GENRE_WORD_RE.search(raw) and (
        re.search(
            r"\b(show|shows|concert|gig|night|going|go\s+to|this\s+weekend|"
            r"saturday|sunday|friday|tonight|tomorrow)\b",
            lowered,
        )
        or re.search(r"\b(seattle|portland|denver|austin|nyc|la)\b", lowered)
        or slots.get("city")
    ):
        return "find_shows"

    if PLAN_RE.search(raw) or (
        TRANSIT_RE.search(raw)
        and (slots.get("city") or re.search(r"\b(seattle|portland|denver|austin)\b", lowered))
        and not _looks_like_artist_lookup(raw)
    ):
        if _count_constraints(raw, slots) >= 2 or PLAN_RE.search(raw):
            return "plan_night"

    if _looks_like_artist_lookup(raw):
        return "find_artist"

    if GENRE_WORD_RE.search(raw) or slots.get("genre") or slots.get("city"):
        if re.search(
            r"\b(show|shows|concert|gig|night|going|go\s+to|this\s+weekend|saturday|tonight)\b",
            lowered,
        ) or slots.get("date_phrase") or slots.get("city"):
            return "find_shows"

    if slots.get("active_ask") in {"find_shows", "plan_night", "find_artist", "refine"}:
        if re.search(r"\b(in\s+\d+\s+days?|this\s+weekend|tomorrow|tonight)\b", lowered):
            return "find_artist" if slots.get("artist") else "refine"
        if len(raw.split()) <= 6 and slots.get("artist") and not GENRE_WORD_RE.search(raw):
            return "find_artist"

    if PLAN_RE.search(raw):
        return "plan_night"

    return "find_shows"


def _count_constraints(text, slots):
    n = 0
    lowered = (text or "").lower()
    if slots.get("city") or re.search(r"\b(seattle|portland|denver|austin|los angeles|nyc)\b", lowered):
        n += 1
    if slots.get("genre") or re.search(r"\b(house|techno|bass|trance|dubstep)\b", lowered):
        n += 1
    if slots.get("date_phrase") or re.search(
        r"\b(tonight|tomorrow|weekend|saturday|sunday|friday|next week|in\s+\d+\s+days?)\b",
        lowered,
    ):
        n += 1
    if TRANSIT_RE.search(lowered) or slots.get("transit_intent") or slots.get("origin"):
        n += 1
    return n


def _looks_like_artist_lookup(text):
    raw = (text or "").strip()
    lowered = raw.lower()
    if re.search(r"\b(who\s+is|what\s+kind)\b", lowered):
        return False
    # Date-only / pronoun follow-ups are not artist lookups
    if re.search(r"\b(in\s+\d+\s+days?)\b", lowered) and len(raw.split()) <= 6:
        cleaned_probe, _ = _strip_city_tokens(raw)
        cleaned_probe = re.sub(
            r"\b(in\s+\d+\s+days?|tonight|tomorrow|this weekend|next weekend|"
            r"it'?s|its|it)\b",
            " ",
            cleaned_probe,
            flags=re.I,
        )
        leftover = [t for t in re.split(r"\W+", cleaned_probe) if t and t.lower() not in STOP_FILLER]
        if not leftover:
            return False
    # "house Saturday Seattle" etc.
    if GENRE_WORD_RE.search(raw):
        return False
    # "Bassvictim seattle show", "Bassvictim seattle", "is Bassvictim playing"
    if re.search(r"\b(show|concert|gig|tour|playing|tickets?)\b", lowered):
        # artist + city/show pattern
        cleaned, _ = _strip_city_tokens(raw)
        tokens = [t for t in re.split(r"\W+", cleaned) if t and t.lower() not in STOP_FILLER and len(t) > 1]
        if 1 <= len(tokens) <= 4:
            return True
    # Short proper-name-ish query without genre words
    if not re.search(r"\b(house|techno|bass|trance|dubstep|edm|shows?)\b", lowered):
        tokens = [t for t in re.split(r"\W+", raw) if t and t.lower() not in STOP_FILLER and len(t) > 1]
        if 1 <= len(tokens) <= 3 and any(t[:1].isupper() or t.islower() for t in tokens):
            # "Bassvictim seattle" after city peel
            cleaned, city = _strip_city_tokens(raw)
            left = [t for t in re.split(r"\W+", cleaned) if t and t.lower() not in STOP_FILLER and len(t) > 1]
            if left and city:
                return True
            if left and len(raw.split()) <= 4 and not re.search(r"\b(weekend|tonight|saturday)\b", lowered):
                return bool(re.search(r"[A-Za-z]{3,}", " ".join(left)))
    return False


def _strip_city_tokens(text):
    aliases = {
        "la": "los angeles", "nyc": "new york", "ny": "new york", "sf": "san francisco",
        "pdx": "portland", "portland": "portland", "seattle": "seattle", "denver": "denver",
        "austin": "austin", "chicago": "chicago", "miami": "miami", "atlanta": "atlanta",
        "boston": "boston", "dallas": "dallas", "houston": "houston", "oakland": "oakland",
        "vegas": "las vegas", "las vegas": "las vegas", "boulder": "boulder",
        "los angeles": "los angeles", "new york": "new york", "san francisco": "san francisco",
    }
    cleaned = " ".join(str(text or "").split())
    city = None
    for phrase in sorted(aliases.keys(), key=len, reverse=True):
        match = re.search(rf"\b{re.escape(phrase)}\b", cleaned, re.I)
        if match:
            city = aliases[phrase.lower()]
            cleaned = (cleaned[:match.start()] + " " + cleaned[match.end():]).strip()
            break
    cleaned = re.sub(r"\b(show|concert|gig|tour|tickets?|playing)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,|/")
    return cleaned, city


def extract_artist_query(text):
    cleaned, city = _strip_city_tokens(text)
    cleaned = re.sub(
        r"\b(in\s+\d+\s+days?|this\s+weekend|next\s+weekend|tonight|tomorrow|saturday|sunday|friday)\b",
        " ",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\b(details?|more\s+info|tell\s+me\s+more)\b", " ", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,|/")
    tokens = [t for t in re.split(r"\W+", cleaned) if t and t.lower() not in STOP_FILLER and len(t) > 1]
    artist = " ".join(tokens).strip() or None
    # Pronouns / empty leftovers from "it's in 2 days"
    if artist and artist.lower() in {"it", "its", "it s", "they", "them", "that", "this", "s"}:
        artist = None
    return artist, city


def extract_compare_target(text):
    match = re.search(
        r"\b(?:compare(?:d)?\s+to|vs\.?|versus)\s+(.+?)[\?!.]*$",
        text or "",
        re.I,
    )
    if match:
        return " ".join(match.group(1).split()).strip() or None
    # "Compare to nighthawk"
    match = re.search(r"\bto\s+([A-Za-z][\w'’.\- ]{1,40})$", (text or "").strip(), re.I)
    if match:
        return match.group(1).strip()
    return None
