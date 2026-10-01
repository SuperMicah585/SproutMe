import json
import os
import logging
import re
from copy import deepcopy
from datetime import datetime, timezone, timedelta, date
from difflib import SequenceMatcher
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo

from services.public_api import compact_event, clean_event_url
from services.artist_heat import heat_breakout, heat_popularity, load_heat_index, match_heat
from services.show_health import score_show
from services.spotify_service import SpotifyCatalog, headliners_for_event
from services.venue_places import load_place_index, match_place, place_cache_row, rank_places, venue_key, venue_score
from services.web_lookup import lookup_context, research_local, research_city_transit
from services.sms_session import (
    SLOTS_ROLE,
    empty_slots,
    filter_public_messages,
    load_slots_from_messages,
    merge_evidence_into_slots,
    upsert_slots_message,
)
from services import sms_intents

logger = logging.getLogger(__name__)

STOP_WORDS = {"stop", "unsubscribe", "cancel", "end", "quit", "remove"}
HELP_WORDS = {"help", "info"}
RESET_WORDS = {"reset"}
SPOTIFY_YES_RE = re.compile(
    r"^(yes|yeah|yep|yup|sure|ok|okay|please|spotify|send it|do it|"
    r"check (them|it|that|those|any|one) out)\b",
    re.I,
)
SPOTIFY_NO_RE = re.compile(r"^(no|nah|nope|not now|skip|later|i'?m good)\b", re.I)
VENUE_ASK_RE = re.compile(
    r"\b(how'?s|how is|reviews?|good venue|worth (it|going)|vibe|sound system|"
    r"what about|is .+ (good|cool|worth))\b",
    re.I,
)
VENUE_RANK_RE = re.compile(
    r"\b(best|top|most popular|highest rated|favorite|go-to)\b.{0,48}\b(venues?|clubs?|rooms?|spots?)\b"
    r"|\b(venues?|clubs?)\b.{0,24}\b(best|most popular|highest rated)\b",
    re.I,
)
VENUE_RANK_FOLLOW_RE = re.compile(
    r"^(most popular|highest rated|best (one|room|club|venue)|top ones?)\??$",
    re.I,
)
SPOTIFY_ORDINALS = {
    "1": 0, "first": 0, "the first": 0, "the first one": 0,
    "2": 1, "second": 1, "the second": 1, "the second one": 1,
    "3": 2, "third": 2, "the third": 2, "the third one": 2,
}
MAX_HISTORY = 12
MAX_TOOL_ROUNDS = 4

MAX_TOOL_ROUNDS_DEEP = 8
JUDGE_MAX_HISTORY = 4
# Recent turns sent to the model + kept after the daily 7am compact.
PROMPT_WINDOW = 20
STORE_SOFT_CAP = 200
COMPACT_MIN_EXTRA = 4
MAX_RULES_CHARS = 1200

JUDGE_JSON_SHAPE = (
    '{"route":"fast_tools"|"deep_lookup",'
    '"confidence":"high"|"medium"|"low",'
    '"reason":"<short why>",'
    '"intent":"search_shows"|"venue_info"|"artist_info"|"verify_claim"|"plan_night"|"meta"|"other",'
    '"city":null|"Seattle",'
    '"neighborhood":null|"Capitol Hill",'
    '"genre":null|"house",'
    '"date_phrase":null|"tonight"|"next weekend",'
    '"artist":null|"Arlo",'
    '"venue":null|"Q Nightclub",'
    '"deep_why":null|"user_challenging_prior_answer"}'
)

JUDGE_SYSTEM_PROMPT = """You are the routing judge for SproutMe SMS (electronic-music show finder).

Your ONLY job: choose how to handle the texter's LATEST message, using recent chat for context.
You do NOT answer the user. You do NOT invent shows, times, prices, or ticket links.

Return ONE JSON object only (no markdown), exactly this shape:
{shape}

Routes:
- fast_tools — simple one-shot catalog asks. Typical: "house in Seattle tonight", "what's at Q", "is Subtronics bass", "best venues in Portland", "the second one", "cheaper", "what stop for Vice?", "which Link stop".
- deep_lookup — richer care + a why-shaped answer. Use when the ask has MULTIPLE real constraints, needs planning/judgment, challenges a prior answer, or a shallow search would feel dismissive.

Prefer deep_lookup when ANY of these are true:
- Multi-constraint planning: 2+ of {{date window, genre, area/neighborhood, transit/access, budget, starting location, vibe}}.
- "Where should I go" / "help me pick" / "I need … so …" style night planning (intent=plan_night).
- Transit or access constraints (light rail, bus, walkable, parking, sober, early show, 18+ vs 21+) when planning where to go — NOT when they only ask which stop for an already-recommended venue.
- They start outside the venue city (e.g. Bellevue → Seattle) and ask where to go.
- They correct a prior bad answer ("those aren't next weekend", "wrong day", "look harder", "are you sure?").
- Verify / challenge turns (intent=verify_claim).
- Ambiguous or research-y asks where inventing a thin fast answer would mislead.

Use fast_tools when a single clear answer is enough — including short follow-ups about a venue just recommended (stop, reviews, "the second one").

Rules:
- When unsure between fast and deep, choose deep_lookup.
- Fill city/neighborhood/genre/date_phrase/artist/venue when clearly stated or strongly implied. Otherwise null.
- date_phrase: copy their words (tonight, next weekend, next week, Saturday) — do not convert to YYYY-MM-DD.
- intent=plan_night for multi-constraint / "where should I" asks.
- intent=verify_claim when they assert a fact or ask the bot to double-check.
- intent=meta for thanks/small-talk (STOP/HELP/RESET are handled outside you).
- confidence=high only when the route choice is obvious.
- reason: one short clause. deep_why: short clause if route is deep_lookup, else null.
- Never invent a home city. If they say "my city" with no city in chat, leave city null.
""".format(shape=JUDGE_JSON_SHAPE)

DEEP_MODE_ADDENDUM = """
DEEP MODE (router selected deep_lookup):
- The texter was already told you are looking into it. Be thorough before answering.

GLOBAL RULE — research local meaning; do not hardcode cities:
- Catalog tools (search_events, etc.) find shows. They do NOT encode city-specific geography, transit, slang, or "what counts as X here".
- Whenever a constraint depends on local knowledge for THIS city — transit/no-car, neighborhood nicknames, "downtown", "close", walkable-from-origin, scene geography, what an area means, etc. — call research_local(city, topic, origin?) to ground it BEFORE you commit to picks.
- Do this for EVERY such constraint in the ask, not only transit. Example topics: "public transit", "Southwest Portland", "Capitol Hill Seattle", "downtown nightlife area".
- Never invent place-specific facts (rail lines, stop names, hood boundaries, which venues are "in" an area) without research_local or lookup_venue support.
- Never expect a per-city distance/matcher database. Optional stop labels on cards are bonuses only — not a filter you can rely on.
- Do not stuff local glosses into search_events q.

Also:
- Ambiguous constraints in the "Resolved constraints" block are planning intents to follow. Still research_local when the meaning is place-specific.
- Answer THEIR question — not a generic ranked dump. Mirror the constraints they named and say how each pick fits.
- Shape: 1–2 short spoken sentences (why these / from-origin transit), blank line, then copy at most TWO `sms.shows` cards unchanged. Do not invent dates, venues, prices, or links.
- If origin is a transit stop (e.g. Judkins), frame access as from that stop to the venue stop ("from Judkins → Westlake") when cards include Link/MAX labels. Do not invent stops.
- If a constraint cannot be met from tools, say that plainly, then offer the closest honest alternative from `later` — never pretend a far-future show is "next weekend".
- If they assert a show/artist/venue/night, search that combination before saying it is missing.
- If catalog tools miss or look thin, call lookup_context. Still never invent a show, date, price, or ticket link.
- Depth is in matching + explaining; keep SMS readable (no essays, no bullet walls).
"""

CONSTRAINT_RESOLVER_SHAPE = (
    '{"ready":true|false,'
    '"clarify_sms":null|"One short clarifying question",'
    '"interpretations":[{"term":"light rail","meaning":"public light rail in this city — deep will research systems","confidence":"high|medium|low","important":true,"research_topic":"public transit"}],'
    '"hints":{"city":"Seattle","genre":"house","date_phrase":"next weekend","neighborhood":null,'
    '"transit":"transit|none|null","origin":"Bellevue"|null,"budget":null,'
    '"research_topics":["public transit","Bellevue to Seattle"]}}'
)

CONSTRAINT_RESOLVER_PROMPT = """You resolve ambiguous planning constraints for SproutMe SMS before tools run.

Return ONE JSON object only (no markdown), exactly this shape:
{shape}

Job:
- Read the latest user message + recent chat.
- Find terms that matter for recommending shows and could be misread as free-text search OR need local grounding (transit, "downtown", "close", "cheap", "early", "the train", neighborhood nicknames, starting suburbs, scene slang, etc.).
- For each important term: interpret the PLANNING INTENT from context, or mark confidence low.
- For place-specific terms, set research_topic (short) and include it in hints.research_topics. Deep mode will call research_local — you do NOT need a hardcoded city encyclopedia.

Rules:
- ready=true only if every IMPORTANT ambiguous term is confidence high or medium as a planning intent (even if deep still needs to research local details).
- If an important term is confidence=low (or city is missing and needed), set ready=false and clarify_sms to ONE short SMS question. Do not ask about things you already know.
- Prefer resolving over asking when intent is clear. Example: "won't have a car" → transit=transit, research_topics includes "public transit", ready=true. Do NOT invent a rail brand for an unknown city.
- Follow-ups like "what stop for Vice?" after a transit rec are NOT ambiguous — ready=true; research_topic can be the venue + transit.
- "I'm in Bellevue … Seattle … light rail" → origin=Bellevue, city=Seattle, transit=transit, research_topics=["public transit","Bellevue Seattle"].
- "staying in Southwest" → origin=Southwest (not a venue filter). research_topics may include that area. Only set hints.neighborhood when they want shows IN that area.
- Never put transit/neighborhood glosses into a search query string — only structured hints + research_topics.
- clarify_sms must be plain SMS (no markdown), under 200 characters.
- hints.date_phrase: copy their words (next weekend, tonight). hints.genre/city when stated.
""".format(shape=CONSTRAINT_RESOLVER_SHAPE)

MAX_SMS_CHARS = 1500
# Carriers often reject long concatenated SMS (Twilio 30019). Keep each part short.
SMS_PART_CHARS = 320
HISTORY_TTL = timedelta(hours=24)
PLACE_CACHE_TTL = timedelta(seconds=60)
ARTIST_HEAT_LIMIT = 12
INTRO_MESSAGE = "SproutMe remembers your taste. Text RESET to clear this chat (keeps preferences). Reply STOP to opt out."
US_TZ = ZoneInfo("America/Los_Angeles")
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
DATE_WORDS_RE = re.compile(
    r"\b(tonight|today|this evening|tomorrow|this weekend|next weekend|this week|next week|"
    r"in\s+\d+\s+days?|"
    r"monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|june?|july?|"
    r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"
    r"|may\s+\d{1,2}"
    r"|20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\b\d{1,2}/\d{1,2}\b",
    re.I,
)
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
CITY_ALIASES = {
    "la": "los angeles",
    "los angeles": "los angeles",
    "dtla": "los angeles",
    "hollywood": "los angeles",
    "santa monica": "los angeles",
    "nyc": "new york",
    "ny": "new york",
    "new york": "new york",
    "new york city": "new york",
    "brooklyn": "new york",
    "manhattan": "new york",
    "queens": "new york",
    "bronx": "new york",
    "sf": "san francisco",
    "san fran": "san francisco",
    "san francisco": "san francisco",
    "pdx": "portland",
    "portland": "portland",
    "dc": "washington",
    "washington dc": "washington",
    "chi": "chicago",
    "philly": "philadelphia",
}
GENRE_FAMILIES = {
    "bass": [
        "bass", "bass music", "dubstep", "riddim", "brostep", "tearout", "color bass",
        "deathstep", "melodic dubstep", "future riddim", "140", "deep dub",
        "drum and bass", "drum n bass", "dnb", "dnB", "jungle", "neurofunk", "liquid dnb",
        "halftime", "breakcore", "footwork", "juke", "trap", "future bass",
        "glitch hop", "glitch-hop", "midtempo", "wave", "uk garage", "ukg", "bassline",
        "grime", "wonky", "bass house",
    ],
    "house": [
        "house", "tech house", "deep house", "afro house", "afrohouse", "progressive house",
        "organic house", "funky house", "latin house", "electro house", "g-house",
        "acid house", "melodic house", "tropical house", "disco", "nu-disco", "italo",
        "amapiano", "garage house",
    ],
    "techno": [
        "techno", "hard techno", "hardgroove", "industrial", "minimal", "melodic techno",
        "acid techno", "dub techno", "peak time", "ebm", "schranz",
    ],
    "trance": ["trance", "psytrance", "psy", "progressive trance", "uplifting trance", "goa"],
    "hard dance": [
        "hardstyle", "hardstyles", "hard dance", "hardcore", "gabber", "uptempo", "rawstyle",
    ],
    "club": [
        "club", "jersey club", "baile funk", "dembow", "reggaeton", "breaks", "breakbeat",
        "electro", "ghetto tech", "ballroom",
    ],
}

SYSTEM_PROMPT = """You are SproutMe, an SMS show finder for electronic music.

Channel: SMS. Replies must stay short. Lock-screen length, not a poster.
- 1 to 3 shows max. Never a long list.
- search_events already ranked 1-3 shows by a single SproutMe score (artist, heat, Google room; missing pieces are dropped and the rest are rescaled; timing only if they named a day). Copy `sms.shows` in that order. Do not rerank.
- Reply like a person texting, not a dashboard. Open with a short spoken answer to THEIR ask, then a blank line and the cards. Do not prefix cards with Name/Room/Hot or dump numbers. In deep mode, the opener should explain why these picks fit their constraints.
- lookup_venue and rank_venues are only for when they ask about a room or the best venues in a city. Do not invent reviews.
- Do not rewrite date, venue, price, or the link. No markdown, no bullets, no emoji walls.
- Never add Spotify songs, track names, or open.spotify links unless they asked to listen.
- Never invent venue reviews, star ratings, or "people say". If they ask how a room is, call lookup_venue and copy `sms`. If they ask the best / top / most popular venue in a city, call rank_venues and copy `sms`. If a tool misses, say you don't have Google notes.
- lookup_artist for artist facts (genre, "are they house") AND listen. Catalog fields first (`catalog_genres`, `sms`). Copy `sms`. Do not invent. If Spotify listen is missing, still send the catalog sms.
- Never say you couldn't find / couldn't pull up an artist or show when a tool returned catalog genres, data, or sms. Answer from that. If catalog and Spotify both miss, call lookup_context. If that misses too, one cautious sentence from general knowledge for identity/genre only — never invent a show, date, price, or ticket link.
- Surrounding questions (what is bass house, who is this DJ, is this a festival act) are fair game. Tools first, then lookup_context. Do not use lookup_context to build a show list.
- bass house is bass, not house. house-only should not return bass house or dubstep.
- If tonight/today is empty but the tool returns `later`, say there is nothing that night, then name the next 1-2 later shows. Do not switch genres.
- Only say nothing matched when `data` and `later` are both empty. If the tool errors but still returns `sms.shows`, copy those. Never invent an empty catalog.
- If `applied.genre_relaxed` is true, say you could not lock that tag cleanly and these are the closest shows in that city. Still copy the cards.

You only recommend real shows from tools. Never invent events.

Relevance:
- Never invent a home city. If they say "my city" / "near me" without naming one, ask which city (e.g. Seattle). Only pass city when THIS message or a recent turn names it.
- Neighborhoods (Capitol Hill, Ballard, Downtown, etc.): pass `neighborhood` plus the parent `city`. search_events filters venues with a structured JSON matcher — copy returned cards; do not invent neighborhood venues.
- Local / ambiguous constraints (transit, no-car, neighborhoods, "downtown", "close", origin areas): in deep mode call research_local(city, topic) for each — do not invent local geography. Pass structured city/genre/date to search_events. Do NOT put those glosses in q. Do NOT expect station-distance filtering.
- Saved genres (if any) are a soft preference. On city/transit follow-ups, keep preferring them unless THIS message names a different genre. Never hard-filter on a genre the texter did not say this turn.
- Subgenres count: bass includes dubstep, riddim, drum and bass, trap, jungle, etc. house includes tech house, afro house, disco. techno includes hard techno and hardgroove. Match the family, not only the exact tag.
- Only hard-filter genre when they name one in this message, and still include that genre's subgenres.
- Clock: US Pacific, for every US texter. Right now it is {now_display}.
- Today is {today_long}. Date key: {today_iso} (event data uses {today_slash}).
- Tonight/today = {today_iso}. Tomorrow = {tomorrow_iso}. This weekend = {weekend}.
- Never recommend a show before today. If they say tonight, search {today_iso}.
- Only pass date when THIS message names a day (tonight, today, tomorrow, Saturday, Oct 8). "Coming", "any", "want to see" means upcoming: omit date.
- Do not reuse tonight/today from earlier messages unless they still mean tonight.
- search_events always includes `later`: upcoming matches after the requested day, same city and genre. If data is empty, answer from `later`. Never drop the genre and fill with a different scene.
- Artist names in q are optional. If they name a city and genre, search those even when the artist is misspelled. Hardstyle includes hardstyles.
- Budgets: pass max_price. Do not put dollar amounts in q. Shows with no listed price are allowed as backups after ones that clearly fit the budget. Do not hide a $10 show because the budget was $30.
- Match taste: house fans should not get trap/pop EDM unless they asked broadly.
- Use earlier messages in this chat for follow-ups like "the second one", "cheaper", or "what about tomorrow". Never keep a tonight filter after they ask for upcoming shows.
- Global rules below are durable taste/style from past chats. Follow them unless this message clearly overrides. Recent messages win for immediate follow-ups.

Tools: search_events, get_event, lookup_artist, lookup_venue, rank_venues, research_local, lookup_context, list_favorites.
"""


COMPACT_RULES_PROMPT = """You maintain durable SMS taste rules for SproutMe (EDM show finder).

Merge the existing rules with the conversation excerpt into an updated rules block.
Keep it under {max_chars} characters. Plain text bullets or short lines only.
Capture only durable signal:
- cities / scenes they care about
- genres (soft vs hard preferences)
- artists or venues they seek or avoid
- how they like replies (short, tonight-first, links, no review fluff, etc.)
- explicit "don't" instructions

Do not invent facts. Drop one-off logistics ("what about tomorrow"). Preserve stable prefs when the excerpt is thin.
Return ONLY the updated rules text, no preamble.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "Search EDM events by city, genre, artist, date, or max ticket price. Returns `data` already ranked by SproutMe score, plus preformatted `sms.shows` to copy. Do not look up Spotify here. Use lookup_venue/rank_venues only if they ask about a room.",
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Artist, venue, or free text. Omit if unsure of spelling. Never put light rail/transit/neighborhood words here."},
                    "city": {"type": "string"},
                    "neighborhood": {"type": "string", "description": "Neighborhood or area within the city, e.g. Capitol Hill, Ballard, Downtown, SoDo. Not the city name."},
                    "genre": {"type": "string", "description": "e.g. hardstyle, house, techno. Plurals are fine."},
                    "date": {"type": "string", "description": "Only if THIS message names a day. YYYY-MM-DD, Oct 8, or tonight. Omit for upcoming."},
                    "max_price": {"type": "number", "description": "Max ticket price in US dollars, e.g. 30. Unpriced shows are still returned as backups."},
                    "limit": {"type": "integer", "default": 5, "maximum": 8},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_event",
            "description": "Get one event by numeric id from search_events.",
            "parameters": {
                "type": "object",
                "required": ["event_id"],
                "properties": {"event_id": {"type": "integer"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_venue",
            "description": "Google notes for a club or venue: rating, review count, and a short summary. Use when they ask how a room is, about reviews, or if a venue is good. Do not invent reviews.",
            "parameters": {
                "type": "object",
                "required": ["venue"],
                "properties": {
                    "venue": {"type": "string", "description": "Venue name, e.g. Vice or Q Nightclub"},
                    "city": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rank_venues",
            "description": "Top music rooms in a city from Google ratings and review counts. Use for best/top/most popular venue in a city. Do not invent a list.",
            "parameters": {
                "type": "object",
                "required": ["city"],
                "properties": {
                    "city": {"type": "string", "description": "City name, e.g. Seattle or Portland"},
                    "limit": {"type": "integer", "default": 3, "maximum": 5},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_artist",
            "description": "Artist facts from the show catalog first (genres, upcoming dates), then Spotify listen if available. Use for genre questions and Spotify requests. Never tell the texter the artist is missing if catalog_genres or sms is present.",
            "parameters": {
                "type": "object",
                "required": ["artist"],
                "properties": {
                    "artist": {"type": "string", "description": "Artist or DJ name, e.g. Subtronics"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_local",
            "description": (
                "Ground place-specific or ambiguous constraints for a city "
                "(transit, neighborhoods, downtown, walkable-from-origin, local area meaning). "
                "Required in deep mode whenever a constraint needs local knowledge — not only transit. "
                "Returns wiki-backed overviews. Not a show catalog and not a venue-distance matcher."
            ),
            "parameters": {
                "type": "object",
                "required": ["city", "topic"],
                "properties": {
                    "city": {"type": "string", "description": "City name, e.g. Portland or Denver"},
                    "topic": {
                        "type": "string",
                        "description": "What to research, e.g. public transit, Southwest Portland, downtown nightlife",
                    },
                    "origin": {
                        "type": "string",
                        "description": "Where they are staying/starting, if relevant",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_context",
            "description": "Look up surrounding context: who a DJ is, what a genre is, whether an act is a festival name. Use after catalog/Spotify/Places miss. Do not use this to invent shows, dates, prices, or ticket links.",
            "parameters": {
                "type": "object",
                "required": ["q"],
                "properties": {
                    "q": {"type": "string", "description": "Artist, genre, or short question, e.g. Bassvictim or bass house"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_favorites",
            "description": "List events this texter has starred in the app.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


class SmsAgent:
    def __init__(
        self,
        *,
        openai_api_key,
        model,
        list_events,
        get_event,
        add_event,
        get_user,
        create_user,
        update_name,
        update_cities,
        update_genres,
        get_favorites,
        delete_user,
        get_conversation=None,
        save_conversation=None,
        delete_conversation=None,
        list_conversations=None,
        spotify=None,
        list_venue_places=None,
        save_venue_place=None,
        list_artist_heat=None,
    ):
        self.openai_api_key = openai_api_key
        self.model = model or "gpt-4.1"
        self.deep_model = (
            os.environ.get("OPENAI_DEEP_MODEL")
            or os.environ.get("OPENAI_DEEP_LOOKUP_MODEL")
            or "gpt-5.4"
        )
        self.list_events = list_events
        self.get_event = get_event
        self.add_event = add_event
        self.get_user = get_user
        self.create_user = create_user
        self.update_name = update_name
        self.update_cities = update_cities
        self.update_genres = update_genres
        self.get_favorites = get_favorites
        self.delete_user = delete_user
        self.get_conversation = get_conversation
        self.save_conversation = save_conversation
        self.delete_conversation = delete_conversation
        self.list_conversations = list_conversations
        self.spotify = spotify if spotify is not None else SpotifyCatalog.from_env()
        self.list_venue_places = list_venue_places
        self.save_venue_place = save_venue_place
        self.list_artist_heat = list_artist_heat
        self._memory = {}
        self._client = None
        self._latest_user_text = ""
        self._last_sms_pack = None
        self._spotify_card_sms = None
        self._place_index = None
        self._place_index_at = None
        self._heat_cache = None
        self._heat_cache_at = None
        self._events_cache = None
        self._events_cache_at = None
        self._artist_heat = {}
        self._neighborhood_cache = {}
        self._last_judgment = None
        self._deep_mode = False
        self._deep_constraints = None
        self._global_rules = ""
        self._conversation_history = []
        self._force_date_from_history = False
        if openai_api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=openai_api_key)
            except ImportError:
                logger.error("openai package is not installed")

    def reply(self, phone_number, body, progress_callback=None):
        text = (body or "").strip()
        self._latest_user_text = text
        self._last_sms_pack = None
        self._spotify_card_sms = None
        self._last_judgment = None
        self._deep_mode = False
        self._deep_constraints = None
        self._session_slots = empty_slots()
        if not text:
            return "Text me a city or genre and I'll find shows. Example: house in Seattle this weekend."

        lowered = text.lower()
        if lowered in STOP_WORDS:
            self._clear_conversation(phone_number)
            return "You're unsubscribed. Text this number again anytime to opt back in. Reply HELP for help."
        if lowered in RESET_WORDS:
            started_at = datetime.now(timezone.utc)
            rules = self._load_global_rules(phone_number)
            self._persist_conversation(phone_number, [], started_at, global_rules=rules, update_rules=True)
            return f"Chat cleared (taste kept). {INTRO_MESSAGE} What city or genre?"
        if lowered in HELP_WORDS:
            return (
                "SproutMe finds EDM shows. Text a city, genre, or artist "
                "(try 'techno in Seattle'). I remember your taste across chats. "
                "Text RESET to clear this chat only. Reply STOP to opt out."
            )

        if not self._client:
            return "SproutMe SMS is not configured yet. Try the site for now: https://sproutme-please.com"

        try:
            user = self._ensure_user(phone_number)
            history, started_at, is_new, global_rules = self._load_conversation(phone_number)
            self._conversation_history = history
            self._global_rules = global_rules or ""

            slots = load_slots_from_messages(history)
            slots = self._merge_slots_from_text(slots, text, history)
            self._session_slots = slots

            intent = sms_intents.classify_intent(text, slots=slots, history=history)
            slots["active_ask"] = intent
            logger.info(
                "sms intent=%s city=%s genre=%s date=%s artist=%s for %s",
                intent,
                slots.get("city"),
                slots.get("genre"),
                slots.get("date_phrase"),
                slots.get("artist"),
                phone_number[-4:] if phone_number else "",
            )

            # Transit-stop follow-ups stay deterministic.
            stop_reply = self._try_transit_stop_answer(text, history)
            if stop_reply:
                return self._finish_turn(
                    phone_number, history, started_at, text, [stop_reply], slots, is_new
                )

            if intent == "out_of_scope":
                msg = (
                    "I'm built for electronic music shows — venues, genres, nights out. "
                    "Try something like house in Seattle Saturday."
                )
                return self._finish_turn(
                    phone_number, history, started_at, text, [msg], slots, is_new
                )

            if intent == "plan_night" and callable(progress_callback):
                try:
                    progress_callback("Looking into options - give me a minute.")
                except Exception:
                    logger.exception("plan_night progress callback failed")

            evidence = self._handle_intent(intent, phone_number, text, slots, history, user)
            parts = self._compose_from_evidence(evidence, intent=intent)
            slots = merge_evidence_into_slots(slots, evidence)
            slots["active_ask"] = intent
            return self._finish_turn(
                phone_number, history, started_at, text, parts, slots, is_new,
                artists=evidence.get("artists"),
            )
        except Exception as exc:
            logger.exception("SMS agent failed for %s", phone_number[-4:] if phone_number else "")
            err = str(exc).lower()
            if "insufficient_quota" in err or "credit_balance" in err:
                return "SproutMe SMS is paused until API credits are added. Use the site for now: https://sproutme-please.com"
            if "429" in err or "rate limit" in err:
                return "Too many texts right now. Try again in a minute?"
            return "I hit a snag looking that up. Try again in a minute?"

    def _finish_turn(self, phone_number, history, started_at, text, parts, slots, is_new, artists=None):
        flat = []
        for part in (parts if isinstance(parts, (list, tuple)) else [parts]):
            if not part:
                continue
            flat.extend(self._split_sms_parts(part))
        if not flat:
            flat = ["I didn't catch that. Try a city or genre?"]
        self._store_turn(phone_number, history, started_at, text, flat, artists, slots=slots)
        return self._with_intro(flat, is_new)

    def _merge_slots_from_text(self, slots, text, history):
        """Merge sticky slots with signals from this message. Never drop unset keys."""
        out = deepcopy(slots or empty_slots())
        raw = text or ""
        lowered = raw.lower()

        if sms_intents.OUT_OF_SCOPE_RE.search(raw):
            return out

        # City
        _, peeled_city = self._peel_city_from_query(raw, None)
        if peeled_city:
            needle = self._city_needle(peeled_city)
            out["city"] = (needle or peeled_city).title()

        # Genre — only when named this turn (avoid matching "club" inside "strip club")
        for family, members in GENRE_FAMILIES.items():
            names = (family, *members)
            for name in sorted(set(names), key=len, reverse=True):
                if len(name) < 3:
                    continue
                if re.search(rf"\b{re.escape(name)}\b", lowered):
                    out["genre"] = family
                    break
            else:
                continue
            break

        # Date phrase
        if DATE_WORDS_RE.search(raw) or re.search(r"\bin\s+\d+\s+days?\b", lowered):
            match = re.search(
                r"\b(in\s+\d+\s+days?|tonight|today|tomorrow|this weekend|next weekend|"
                r"this week|next week|saturday|sunday|friday|thursday|wednesday|tuesday|monday)\b",
                lowered,
            )
            if match:
                out["date_phrase"] = match.group(1)

        # Transit / origin
        if sms_intents.TRANSIT_RE.search(raw):
            out["transit_intent"] = True
        origin_hit = self._resolve_origin_station(out.get("city") or "", latest=raw)
        if origin_hit:
            out["origin"] = origin_hit[0]
            out["transit_intent"] = True
        if re.search(r"\b(staying\s+in|live(?:s)?\s+(?:near|close to)|close to the)\b", lowered):
            _, hood = self._peel_neighborhood(raw, out.get("city"))
            if hood and not out.get("origin"):
                out["origin"] = hood

        # New genre browse clears prior artist topic
        if out.get("genre") and (
            out.get("city") or out.get("date_phrase")
        ) and not sms_intents._looks_like_artist_lookup(raw):
            out["artist"] = None

        # Artist — only for artist-shaped asks (don't poison find_shows)
        if sms_intents._looks_like_artist_lookup(raw):
            artist, artist_city = sms_intents.extract_artist_query(raw)
            if artist_city:
                out["city"] = artist_city.title()
            if artist:
                out["artist"] = artist
        elif out.get("artist") and re.search(r"\bin\s+\d+\s+days?\b", lowered):
            # Keep sticky artist; only peel city if present
            _, artist_city = sms_intents.extract_artist_query(raw)
            if artist_city:
                out["city"] = artist_city.title()

        # "reload details" → sticky subject for honest refine
        if sms_intents.DETAILS_RE.search(raw) and not out.get("artist"):
            subj = re.sub(
                r"\b(details?|more\s+info|tell\s+me\s+more|what'?s\s+it\s+like)\b",
                " ",
                raw,
                flags=re.I,
            )
            subj_artist, _ = sms_intents.extract_artist_query(subj)
            if subj_artist:
                out["artist"] = subj_artist
                out["venue"] = out.get("venue") or subj_artist

        # Festival / lineup target
        boo = re.search(r"\b(boo(?:\s+seattle)?)\b", lowered)
        if boo and re.search(r"\b(lineup|artists?|who'?s\s+playing|who\s+plays)\b", lowered):
            out["artist"] = "BOO Seattle"

        compare = sms_intents.extract_compare_target(raw)
        if compare:
            out["compare_to"] = compare

        # Neighborhood only when asking shows IN area (not "in 2 days")
        if not re.search(r"\b(staying\s+in|live(?:s)?\s+near|in\s+\d+\s+days?)\b", lowered):
            _, hood = self._peel_neighborhood(raw, out.get("city"))
            if hood and len(str(hood)) >= 3 and re.search(r"\b(in|near|around)\b", lowered):
                out["neighborhood"] = hood

        return out

    def _handle_intent(self, intent, phone_number, text, slots, history, user):
        if intent == "find_artist":
            return self._evidence_find_artist(slots, text)
        if intent == "entity_info":
            return self._evidence_entity_info(slots, text)
        if intent == "refine":
            return self._evidence_refine(phone_number, slots, text)
        if intent == "plan_night":
            return self._evidence_plan_night(phone_number, slots, text, user)
        # find_shows default
        return self._evidence_find_shows(phone_number, slots, text)

    def _evidence_find_artist(self, slots, text):
        artist = slots.get("artist") or sms_intents.extract_artist_query(text)[0]
        city = slots.get("city")
        date_phrase = slots.get("date_phrase")
        if not artist:
            return self._honest_miss(
                "Which artist? Try something like 'Bassvictim Seattle'.",
                slots=slots,
            )
        start, end = self._parse_date_window(date_phrase or "")
        hits = self._artist_events(artist, limit=20)
        if city:
            city_l = self._city_needle(city)
            hits = [e for e in hits if self._city_hit(e, city_l)]
        in_window = []
        later = []
        today = self._clock()["today"]
        for event in hits:
            day = self._event_date(event)
            if day and day < today:
                continue
            if start and day and self._in_date_window(day, start, end):
                in_window.append(event)
            else:
                later.append(event)
        data = in_window or ([] if start else hits[:2])
        later_out = later[:2] if not in_window and start else (later[:1] if in_window else later[1:3])
        if not data and not later_out:
            where = f" in {city}" if city else ""
            when = f" for {date_phrase}" if date_phrase else ""
            return self._honest_miss(
                f"I don't have a cataloged {artist} show{where}{when}.",
                slots=slots,
                applied={"artist": artist, "city": city, "date_phrase": date_phrase},
            )
        use = data[:2] if data else later_out[:2]
        cards = [self._format_sms_show(e) for e in use]
        if data:
            opener = f"Found {artist}" + (f" in {city}" if city else "") + ":"
        else:
            opener = (
                f"Nothing for {artist}"
                + (f" in {city}" if city else "")
                + (f" {date_phrase}" if date_phrase else "")
                + ". Closest upcoming:"
            )
        return {
            "ok": True,
            "opener": opener,
            "shows": use,
            "later": [],
            "cards": cards,
            "artists": self._show_artists(use),
            "applied": {
                "artist": artist,
                "city": city,
                "date_phrase": date_phrase,
                "genre": None,
            },
            "miss_reason": None,
        }

    def _evidence_find_shows(self, phone_number, slots, text, soft_genre=True):
        args = self._slots_to_search_args(slots)
        # Sticky date/genre must survive even when this message omits them.
        prior = self._latest_user_text
        sticky_bits = [text or ""]
        if slots.get("date_phrase") and not DATE_WORDS_RE.search(text or ""):
            sticky_bits.append(slots["date_phrase"])
        if slots.get("genre") and not self._text_mentions_genre(text or "", slots["genre"]):
            sticky_bits.append(slots["genre"])
        if slots.get("city") and not self._city_needle(slots["city"]) in (text or "").lower():
            sticky_bits.append(slots["city"])
        self._latest_user_text = " ".join(sticky_bits)
        self._slots_driven = True
        try:
            result = self._search_for_texter(phone_number, args)
        finally:
            self._latest_user_text = prior
            self._slots_driven = False
        return self._pack_search_result(result, slots, text)

    def _evidence_refine(self, phone_number, slots, text):
        lowered = (text or "").lower()
        # "the second one"
        idx_match = re.search(r"\b(first|1st|second|2nd|third|3rd)\b", lowered)
        if idx_match and slots.get("last_cards"):
            order = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2}
            idx = order.get(idx_match.group(1), 0)
            cards = slots.get("last_cards") or []
            if idx < len(cards):
                return {
                    "ok": True,
                    "opener": "That one:",
                    "shows": [],
                    "later": [],
                    "cards": [cards[idx]],
                    "artists": [],
                    "applied": {
                        "city": slots.get("city"),
                        "genre": slots.get("genre"),
                        "date_phrase": slots.get("date_phrase"),
                    },
                    "miss_reason": None,
                }

        # Details on last recommendation without inventing
        if sms_intents.DETAILS_RE.search(text or "") and not sms_intents.COMPARE_RE.search(text or ""):
            cards = slots.get("last_cards") or []
            if not cards:
                # Named subject with no prior cards — catalog only, no vibe fluff
                subject = slots.get("artist") or slots.get("venue")
                if subject:
                    events = self._artist_events(subject, limit=2)
                    if events:
                        return {
                            "ok": True,
                            "opener": (
                                f"Here's the {subject} listing from the catalog. "
                                "I don't have deeper vibe/lineup notes beyond the card."
                            ),
                            "shows": events[:1],
                            "later": [],
                            "cards": [self._format_sms_show(events[0])],
                            "artists": [],
                            "applied": {
                                "artist": subject,
                                "city": slots.get("city"),
                            },
                            "miss_reason": None,
                        }
                return self._honest_miss(
                    "I don't have more catalog details on that one beyond the listing.",
                    slots=slots,
                )
            return {
                "ok": True,
                "opener": (
                    "Here's the listing I have. I don't have a deeper lineup pull "
                    "beyond what's on the card."
                ),
                "shows": [],
                "later": [],
                "cards": cards[:2],
                "artists": [],
                "applied": {
                    "city": slots.get("city"),
                    "genre": slots.get("genre"),
                    "date_phrase": slots.get("date_phrase"),
                },
                "miss_reason": None,
            }

        # Compare — re-retrieve with sticky genre/date/city
        compare = slots.get("compare_to") or sms_intents.extract_compare_target(text or "")
        if compare:
            slots = deepcopy(slots)
            # Keep genre sticky; search again
            pack = self._evidence_find_shows(phone_number, slots, text)
            if not pack.get("ok"):
                return pack
            opener = (
                f"Still filtering to {slots.get('genre') or 'your'} shows"
                if slots.get("genre")
                else "Comparing with the same filters"
            )
            opener += f" (vs {compare})."
            # Prefer card mentioning compare target
            cards = pack.get("cards") or []
            preferred = [c for c in cards if compare.lower() in (c or "").lower()]
            if preferred:
                cards = preferred + [c for c in cards if c not in preferred]
            pack["cards"] = cards[:2]
            pack["opener"] = opener
            return pack

        # Date/city refinement on prior artist ask
        if slots.get("artist"):
            return self._evidence_find_artist(slots, text)
        return self._evidence_find_shows(phone_number, slots, text)

    def _evidence_entity_info(self, slots, text):
        artist = slots.get("artist")
        lineup_ask = bool(re.search(
            r"\b(lineup|who'?s\s+(playing|on)|who\s+plays|main\s+artists?)\b",
            text or "",
            re.I,
        ))
        who = re.search(r"\bwho\s+is\s+(.+?)[\?!.]*$", text or "", re.I)
        if who:
            artist = who.group(1).strip()
        if lineup_ask:
            boo = re.search(r"\b(boo(?:\s+seattle)?)\b", text or "", re.I)
            if boo:
                artist = "BOO Seattle"
            elif not artist:
                artist, _ = sms_intents.extract_artist_query(
                    re.sub(
                        r"\b(main\s+artists?|lineup|who'?s\s+playing|who\s+plays|at|the)\b",
                        " ",
                        text or "",
                        flags=re.I,
                    )
                )
            target = artist or slots.get("venue") or ""
            if not target and slots.get("last_cards"):
                first = (slots["last_cards"][0] or "").split("\n")[0]
                target = re.sub(r"^[A-Za-z]{3}\s+\d{1,2}/\d{1,2}:\s*", "", first).strip()
            events = self._artist_events(target, limit=5) if target else []
            if slots.get("city") and events:
                city_l = self._city_needle(slots["city"])
                events = [e for e in events if self._city_hit(e, city_l)] or events
            if not events:
                return self._honest_miss(
                    f"I couldn't pull a reliable lineup for {target or 'that show'} from the catalog.",
                    slots=slots,
                )
            # Headliners from catalog only — never invent substitutes
            names = []
            for event in events[:1]:
                for name in headliners_for_event(event, limit=5):
                    if name and name.lower() not in {t.lower() for t in names}:
                        names.append(name)
            if not names or (len(names) == 1 and names[0].lower() == (target or "").lower()):
                cards = [self._format_sms_show(events[0])]
                return {
                    "ok": True,
                    "opener": (
                        f"I have the {target} listing, but no separate headliner list "
                        "in the catalog — not going to guess."
                    ),
                    "shows": events[:1],
                    "later": [],
                    "cards": cards,
                    "artists": [],
                    "applied": {"artist": target, "city": slots.get("city")},
                    "miss_reason": None,
                }
            opener = f"From the catalog: {', '.join(names[:5])}."
            return {
                "ok": True,
                "opener": opener,
                "shows": events[:1],
                "later": [],
                "cards": [self._format_sms_show(events[0])],
                "artists": names[:3],
                "applied": {"artist": target, "city": slots.get("city")},
                "miss_reason": None,
            }

        if not artist:
            return self._honest_miss("Which artist should I look up?", slots=slots)
        catalog = self._catalog_artist_card(artist) or {}
        card = {}
        if getattr(self.spotify, "enabled", False):
            try:
                card = self.spotify.lookup_artist(artist) or {}
            except Exception:
                logger.exception("spotify lookup failed")
        genres = catalog.get("genres") or card.get("genres") or []
        sms = catalog.get("sms") or card.get("sms") or ""
        if not genres and not sms:
            # Evidence gate: no catalog/Spotify fact → honest miss (never invent vibe)
            return self._honest_miss(
                f"I don't have solid catalog notes on {artist}.",
                slots=slots,
            )
        if genres and not sms:
            opener = f"{artist}: {', '.join(genres[:4])}."
        else:
            opener = sms
        # Attach next show card if we have one in same city
        events = self._artist_events(artist, limit=3)
        if slots.get("city"):
            city_l = self._city_needle(slots["city"])
            city_hits = [e for e in events if self._city_hit(e, city_l)]
            events = city_hits or events
        cards = [self._format_sms_show(events[0])] if events else []
        return {
            "ok": True,
            "opener": opener,
            "shows": events[:1],
            "later": [],
            "cards": cards,
            "artists": [artist],
            "applied": {"artist": artist, "city": slots.get("city")},
            "miss_reason": None,
        }

    def _evidence_plan_night(self, phone_number, slots, text, user):
        """Retrieve candidates first; LLM may only narrate over evidence."""
        self._deep_mode = True
        pack = self._evidence_find_shows(phone_number, slots, text)
        if not pack.get("ok"):
            return pack
        # Optional local research for transit/origin — does not invent shows
        research_bits = []
        if slots.get("transit_intent") and slots.get("city"):
            try:
                research = research_local(
                    slots["city"],
                    topic="public transit",
                    origin=slots.get("origin") or "",
                )
                if research.get("found") and research.get("sms"):
                    research_bits.append(research["sms"])
            except Exception:
                logger.exception("research_local failed")
        opener = self._plan_night_opener(text, pack, slots, research_bits, user)
        pack["opener"] = opener or pack.get("opener")
        pack["cards"] = (pack.get("cards") or [])[:2]
        return pack

    def _plan_night_opener(self, text, pack, slots, research_bits, user):
        if not self._client:
            return pack.get("opener")
        cards = pack.get("cards") or []
        if not cards:
            return pack.get("opener")
        system = (
            "You write ONE short SMS opener (1-2 sentences) for SproutMe. "
            "Only reference the provided show cards and research notes. "
            "Never invent shows, venues, stops, prices, or lineups. "
            "No markdown. Plain text."
        )
        user_msg = (
            f"User ask: {text}\n"
            f"Slots: city={slots.get('city')} genre={slots.get('genre')} "
            f"date={slots.get('date_phrase')} origin={slots.get('origin')} "
            f"transit={slots.get('transit_intent')}\n"
            f"Cards:\n" + "\n---\n".join(cards[:2]) + "\n"
        )
        if research_bits:
            user_msg += "Research notes:\n" + "\n".join(research_bits[:2])
        try:
            response = self._chat_completion(
                model=self.deep_model or self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
                max_tokens=120,
            )
            opener = (response.choices[0].message.content or "").strip()
            opener = self._gsm_safe_sms(opener)
            if 12 <= len(opener) <= 280:
                return opener
        except Exception:
            logger.exception("plan_night opener failed")
        return pack.get("opener")

    def _slots_to_search_args(self, slots):
        args = {"limit": 5}
        if slots.get("city"):
            args["city"] = slots["city"]
        if slots.get("genre"):
            args["genre"] = slots["genre"]
        if slots.get("date_phrase"):
            args["date"] = slots["date_phrase"]
        if slots.get("neighborhood") and not slots.get("transit_intent"):
            hood = str(slots["neighborhood"])
            if len(hood) >= 3 and not hood.isdigit():
                args["neighborhood"] = hood
        # Never pass free-text artist leftovers into show search q
        return args

    def _pack_search_result(self, result, slots, text):
        if not isinstance(result, dict):
            try:
                result = json.loads(result) if isinstance(result, str) else {}
            except (TypeError, json.JSONDecodeError):
                result = {}
        data = list(result.get("data") or [])[:2]
        later = list(result.get("later") or [])[:1]
        sms = result.get("sms") or {}
        cards = list(sms.get("shows") or [])[:2]
        if not cards and data:
            cards = [self._format_sms_show(e) for e in data]
        if not data and later:
            cards = [self._format_sms_show(e) for e in later[:2]]
        applied = dict(result.get("applied") or {})
        applied.setdefault("city", slots.get("city"))
        applied.setdefault("genre", slots.get("genre") or applied.get("genre"))
        applied["date_phrase"] = slots.get("date_phrase")
        if not data and not later and not cards:
            place = slots.get("city") or "that city"
            genre = slots.get("genre")
            when = slots.get("date_phrase")
            bits = [f"No{' ' + genre if genre else ''} shows found in {place}"]
            if when:
                bits[0] += f" for {when}"
            bits[0] += "."
            return self._honest_miss(bits[0], slots=slots, applied=applied)
        genre = slots.get("genre")
        place = slots.get("city") or "that city"
        when = slots.get("date_phrase")
        if data:
            opener = f"For {when + ' ' if when else ''}{genre + ' ' if genre else ''}in {place}".strip()
            opener = re.sub(r"\s+", " ", opener).strip()
            if opener.lower().startswith("for in "):
                opener = f"Shows in {place}"
            elif not opener.lower().startswith("for "):
                opener = f"For {opener}" if when or genre else f"Shows in {place}"
            opener = opener.rstrip(":") + ":"
        else:
            opener = (
                f"Nothing{' ' + genre if genre else ''} in {place}"
                f"{' ' + when if when else ''}. Closest upcoming:"
            )
        # Soft-prefer saved taste only reflected in ranking already
        self._last_sms_pack = {
            "shows": cards,
            "later": [self._format_sms_show(e) for e in later],
            "artists": self._show_artists(data or later),
            "place": place,
            "wanted_day": applied.get("date"),
            "opener": opener,
            "deep": bool(getattr(self, "_deep_mode", False)),
            "transit": bool(slots.get("transit_intent")),
            "origin": slots.get("origin"),
        }
        return {
            "ok": True,
            "opener": opener,
            "shows": data,
            "later": later,
            "cards": cards,
            "artists": self._show_artists(data or later),
            "applied": applied,
            "miss_reason": None,
        }

    def _honest_miss(self, message, slots=None, applied=None):
        return {
            "ok": False,
            "opener": self._gsm_safe_sms(message),
            "shows": [],
            "later": [],
            "cards": [],
            "artists": [],
            "applied": applied or {
                "city": (slots or {}).get("city"),
                "genre": (slots or {}).get("genre"),
                "date_phrase": (slots or {}).get("date_phrase"),
                "artist": (slots or {}).get("artist"),
            },
            "miss_reason": message,
        }

    def _compose_from_evidence(self, evidence, intent=None):
        """Build SMS parts from evidence only — never freeform model shows."""
        evidence = evidence or {}
        opener = self._gsm_safe_sms((evidence.get("opener") or "").strip())
        cards = [self._gsm_safe_sms(c) for c in (evidence.get("cards") or [])[:2] if c]
        if not cards:
            return [opener or "I don't have a catalog match for that."]
        if opener:
            # Keep opener + first card together when short enough
            first = f"{opener}\n\n{cards[0]}"
            parts = [first]
            parts.extend(cards[1:])
            return parts
        return cards

    def _deep_ack_sms(self, judgment):
        intent = (judgment or {}).get("intent") or ""
        if intent == "verify_claim":
            return "On it - double-checking that now."
        if intent == "plan_night":
            return "Looking into options - give me a minute."
        return "Looking that up - give me a minute."

    def _resolve_deep_constraints(self, text, history, judgment=None):
        """Interpret ambiguous planning terms before tools. Ask one SMS question if unsure."""
        default = {
            "ready": True,
            "clarify_sms": None,
            "interpretations": [],
            "hints": {},
        }
        if not self._client:
            return default

        recent = []
        for item in (history or [])[-JUDGE_MAX_HISTORY:]:
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = (item.get("content") or "").strip()
            if content:
                recent.append(f"{role}: {content[:350]}")
        transcript = "\n".join(recent) if recent else "(no prior turns)"
        judge_bits = []
        for key in ("city", "neighborhood", "genre", "date_phrase", "intent"):
            if (judgment or {}).get(key):
                judge_bits.append(f"{key}={(judgment or {}).get(key)}")
        user_msg = (
            f"Recent chat:\n{transcript}\n\n"
            f"Router hints: {'; '.join(judge_bits) if judge_bits else '(none)'}\n\n"
            f"Latest user message:\n{(text or '').strip()}"
        )
        model = (
            os.environ.get("OPENAI_CONSTRAINT_MODEL")
            or getattr(self, "deep_model", None)
            or self.model
        )
        try:
            response = self._chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": CONSTRAINT_RESOLVER_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=450,
            )
            raw = (response.choices[0].message.content or "").strip()
            payload = json.loads(raw) if raw else {}
        except Exception:
            logger.exception("deep constraint resolve failed; continuing ready")
            return default

        interpretations = []
        for item in payload.get("interpretations") or []:
            if not isinstance(item, dict):
                continue
            term = " ".join(str(item.get("term") or "").split()).strip()
            meaning = " ".join(str(item.get("meaning") or "").split()).strip()
            confidence = str(item.get("confidence") or "low").strip().lower()
            if confidence not in {"high", "medium", "low"}:
                confidence = "low"
            if not term:
                continue
            entry = {
                "term": term,
                "meaning": meaning or term,
                "confidence": confidence,
                "important": bool(item.get("important", True)),
            }
            research_topic = " ".join(str(item.get("research_topic") or "").split()).strip()
            if research_topic:
                entry["research_topic"] = research_topic
            interpretations.append(entry)

        hints_in = payload.get("hints") if isinstance(payload.get("hints"), dict) else {}
        hints = {}
        for key in ("city", "genre", "date_phrase", "neighborhood", "transit", "origin", "budget"):
            value = hints_in.get(key)
            if value is None:
                continue
            text_value = " ".join(str(value).split()).strip()
            if not text_value or text_value.lower() in {"null", "none", "n/a"}:
                continue
            hints[key] = text_value

        ready = bool(payload.get("ready", True))
        clarify = " ".join(str(payload.get("clarify_sms") or "").split()).strip() or None
        # Seattle + "light rail/link" → transit intent; deep still researches, no matcher required.
        blob = f"{text} {hints.get('city') or ''} {(judgment or {}).get('city') or ''}".lower()
        if re.search(r"\b(light\s*rail|link)\b", blob) and re.search(
            r"\b(seattle|bellevue|redmond|capitol hill|sea\b)\b",
            blob,
        ):
            interpretations = [
                item for item in interpretations
                if "light rail" not in item["term"].lower() and item["term"].lower() != "link"
            ] + [{
                "term": "light rail",
                "meaning": "public light rail access (research Seattle systems)",
                "confidence": "high",
                "important": True,
                "research_topic": "Seattle Link light rail",
            }]
            hints.setdefault("city", "Seattle")
            hints["transit"] = "transit"
            ready = True
            clarify = None

        # No-car / car-free → transit intent; deep researches the city's systems.
        no_car = bool(re.search(
            r"\b((?:no|without)\s+(?:a\s+)?car|"
            r"(?:won'?t|wont|don'?t|dont)\s+have\s+(?:a\s+)?car|car[- ]?free)\b",
            blob,
        ))
        if no_car:
            interpretations = [
                item for item in interpretations
                if "car" not in item["term"].lower()
            ] + [{
                "term": "no car",
                "meaning": "needs public transit / walkable venues (research local systems)",
                "confidence": "high",
                "important": True,
                "research_topic": "public transit",
            }]
            hints["transit"] = "transit"
            ready = True
            clarify = None

        # Normalize SW Portland neighborhood label.
        hood = (hints.get("neighborhood") or "").strip().lower()
        if hood in {"sw", "s.w.", "southwest", "south west"} and (
            "portland" in blob or "portland" in (hints.get("city") or "").lower()
        ):
            hints["neighborhood"] = "Southwest"
            hints.setdefault("city", "Portland")

        # "staying in X" / "I'm in X" is origin, not a venue neighborhood filter.
        if re.search(
            r"\b(staying\s+in|i'?m\s+in|im\s+in|i\s+am\s+in|based\s+in|coming\s+from)\b",
            blob,
        ):
            origin_place = hints.get("origin") or hints.get("neighborhood")
            if origin_place:
                hints["origin"] = origin_place
            if not re.search(
                r"\b(shows?|events?|gigs?|nightlife)\s+in\b|\bin\s+(the\s+)?(southwest|southeast|northeast|northwest|downtown|ballard|capitol hill)\b.*\b(shows?|events?|tonight|weekend)\b",
                blob,
            ):
                hints.pop("neighborhood", None)

        # Collect research topics for deep mode (global — not transit-only).
        research_topics = []
        for item in interpretations:
            topic = " ".join(str(item.get("research_topic") or "").split()).strip()
            if topic:
                research_topics.append(topic)
        for raw in hints_in.get("research_topics") or []:
            topic = " ".join(str(raw or "").split()).strip()
            if topic:
                research_topics.append(topic)
        if hints.get("transit") and hints.get("transit") != "none":
            research_topics.append("public transit")
        if hints.get("origin"):
            city_bit = hints.get("city") or ""
            research_topics.append(
                f"{hints['origin']} {city_bit}".strip()
                if city_bit else str(hints["origin"])
            )
        # de-dupe preserve order
        seen_topics = set()
        ordered_topics = []
        for topic in research_topics:
            key = topic.lower()
            if key in seen_topics:
                continue
            seen_topics.add(key)
            ordered_topics.append(topic)
        if ordered_topics:
            hints["research_topics"] = ordered_topics

        # If any important interpretation is still low-confidence, force a clarify.
        for item in interpretations:
            if item.get("important") and item.get("confidence") == "low":
                ready = False
                if not clarify:
                    clarify = f"Quick check — when you say {item['term']}, what do you mean?"
                break

        if not ready and not clarify:
            clarify = "Quick check — what did you mean there so I search the right thing?"

        out = {
            "ready": ready,
            "clarify_sms": None if ready else clarify,
            "interpretations": interpretations,
            "hints": hints,
        }
        logger.info(
            "deep constraints ready=%s transit=%s city=%s interpretations=%s",
            out["ready"],
            hints.get("transit"),
            hints.get("city"),
            [(i.get("term"), i.get("confidence")) for i in interpretations],
        )
        return out

    def _constraints_prompt_block(self, constraints):
        if not constraints or not constraints.get("ready"):
            return ""
        lines = ["Resolved constraints (follow these; do not put glosses in q):"]
        for item in constraints.get("interpretations") or []:
            lines.append(
                f"- {item.get('term')}: {item.get('meaning')} "
                f"(confidence={item.get('confidence')})"
            )
        hints = constraints.get("hints") or {}
        if hints:
            bits = [f"{k}={v}" for k, v in hints.items() if v]
            if bits:
                lines.append("Search hints: " + "; ".join(bits))
        lines.append(
            "Call search_events with structured city/genre/date only. "
            "For place-specific constraints, call research_local(city, topic) "
            f"for each topic before final picks"
            + (
                f" (suggested: {', '.join((constraints.get('hints') or {}).get('research_topics') or [])})"
                if (constraints.get("hints") or {}).get("research_topics")
                else ""
            )
            + ". Do not expect a per-city matcher database."
        )
        return "\n".join(lines)

    def _constraint_flags(self, text):
        raw = text or ""
        lowered = raw.lower()
        flags = {
            "date": bool(DATE_WORDS_RE.search(raw) or re.search(
                r"\b(next weekend|this weekend|next week|next friday|next saturday)\b",
                lowered,
            )),
            "genre": any(
                re.search(rf"\b{re.escape(name)}\b", lowered)
                for family, members in GENRE_FAMILIES.items()
                for name in (family, *members)
                if len(name) >= 3
            ),
            "area": bool(re.search(
                r"\b(downtown|capitol hill|cap hill|ballard|beacon hill|fremont|"
                r"queen anne|sodo|belltown|u-?district|georgetown|neighborhood|"
                r"southwest|southeast|northeast|northwest|\bsw\b|\bse\b|\bne\b|\bnw\b|"
                r"near|close to|around)\b",
                lowered,
            )),
            "transit": bool(re.search(
                r"\b(light\s*rail|link|bus|transit|uber|lyft|parking|walkable|"
                r"public\s+transport|metro|train|ferry|car[- ]?free|stations?|"
                r"(?:no|without)\s+(?:a\s+)?car|"
                r"(?:won'?t|wont|don'?t|dont)\s+have\s+(?:a\s+)?car)\b",
                lowered,
            )),
            "origin": bool(re.search(
                r"\b(i'?m in|im in|i am in|staying in|coming from|drive from|coming out of)\b|"
                r"\bfrom\s+(bellevue|redmond|kirkland|tacoma|everett|renton|olympia)\b",
                lowered,
            )),
            "plan": bool(re.search(
                r"\b(where should i|where can i|help me (pick|choose|find)|"
                r"i need|so (that|i)|looking for|recommend|what('?s| is) good)\b",
                lowered,
            )),
            "budget": bool(re.search(r"\$\s*\d+|\b(under|below|max|budget|cheap|affordable)\b", lowered)),
            "correction": bool(re.search(
                r"\b(aren'?t|isn'?t|wrong|not (next|this)|those aren'?t|look harder|"
                r"are you sure|you (said|missed)|actually)\b",
                lowered,
            )),
        }
        return flags

    def _should_prefer_deep(self, text, history, judgment=None):
        flags = self._constraint_flags(text)
        constraint_count = sum(
            1 for key in ("date", "genre", "area", "transit", "origin", "budget")
            if flags.get(key)
        )
        intent = ((judgment or {}).get("intent") or "").strip().lower()
        if intent in {"plan_night", "verify_claim"}:
            return True, "intent_" + intent
        if flags.get("correction"):
            return True, "correction"
        if flags.get("plan") and constraint_count >= 1:
            return True, "plan_plus_constraint"
        if flags.get("transit") and (flags.get("date") or flags.get("genre") or flags.get("plan")):
            return True, "transit_multi"
        if flags.get("origin") and (flags.get("date") or flags.get("genre") or flags.get("plan")):
            return True, "origin_multi"
        if constraint_count >= 3:
            return True, f"multi_constraint_{constraint_count}"
        # Recent assistant missed a date and they are still planning.
        recent_assistant = ""
        for item in reversed(history or []):
            if item.get("role") == "assistant":
                recent_assistant = (item.get("content") or "").lower()
                break
        if flags.get("date") and recent_assistant and re.search(
            r"\b(don'?t have|nothing|no (house )?shows?|aren'?t actually|wrong)\b",
            recent_assistant,
        ):
            return True, "after_empty_or_miss"
        return False, ""

    def _maybe_upgrade_to_deep(self, text, history, judgment):
        judgment = dict(judgment or {})
        if judgment.get("route") == "deep_lookup":
            return judgment
        prefer, why = self._should_prefer_deep(text, history, judgment)
        if not prefer:
            return judgment
        judgment["route"] = "deep_lookup"
        judgment["intent"] = judgment.get("intent") if judgment.get("intent") not in {None, "", "other", "search_shows"} else "plan_night"
        if judgment["intent"] == "search_shows" and why.startswith(("multi_", "plan_", "transit_", "origin_")):
            judgment["intent"] = "plan_night"
        judgment["deep_why"] = why
        judgment["reason"] = f"upgraded_to_deep:{why}"
        judgment["confidence"] = "medium"
        logger.info("sms judge upgraded to deep_lookup (%s)", why)
        return judgment

    def _judge_route(self, text, history):
        """LLM router for every inbound SMS (except STOP/HELP/RESET)."""
        default = {
            "route": "fast_tools",
            "confidence": "low",
            "reason": "judge_fallback",
            "intent": "other",
            "city": None,
            "neighborhood": None,
            "genre": None,
            "date_phrase": None,
            "artist": None,
            "venue": None,
            "deep_why": None,
        }
        if not self._client:
            return default

        recent = []
        for item in (history or [])[-JUDGE_MAX_HISTORY:]:
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = (item.get("content") or "").strip()
            if not content:
                continue
            recent.append(f"{role}: {content[:400]}")
        transcript = "\n".join(recent) if recent else "(no prior turns)"
        user_msg = (
            f"Recent chat:\n{transcript}\n\n"
            f"Latest user message:\n{(text or '').strip()}"
        )
        model = os.environ.get("OPENAI_JUDGE_MODEL") or "gpt-4.1-mini"
        try:
            response = self._chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=220,
            )
            raw = (response.choices[0].message.content or "").strip()
            payload = json.loads(raw) if raw else {}
        except Exception:
            logger.exception("sms judge failed; defaulting to fast_tools")
            return default

        route = str(payload.get("route") or "fast_tools").strip().lower()
        if route not in {"fast_tools", "deep_lookup"}:
            route = "fast_tools"
        confidence = str(payload.get("confidence") or "low").strip().lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        intent = str(payload.get("intent") or "other").strip().lower()
        allowed_intent = {
            "search_shows", "venue_info", "artist_info", "verify_claim",
            "plan_night", "meta", "other",
        }
        if intent not in allowed_intent:
            intent = "other"

        def clean_field(value):
            if value is None:
                return None
            text_value = " ".join(str(value).split()).strip()
            if not text_value or text_value.lower() in {"null", "none", "n/a"}:
                return None
            return text_value

        out = {
            "route": route,
            "confidence": confidence,
            "reason": clean_field(payload.get("reason")) or "n/a",
            "intent": intent,
            "city": clean_field(payload.get("city")),
            "neighborhood": clean_field(payload.get("neighborhood")),
            "genre": clean_field(payload.get("genre")),
            "date_phrase": clean_field(payload.get("date_phrase")),
            "artist": clean_field(payload.get("artist")),
            "venue": clean_field(payload.get("venue")),
            "deep_why": clean_field(payload.get("deep_why")),
        }
        return out

    def _judgment_prompt_block(self, judgment):
        if not judgment:
            return ""
        bits = [
            f"route={judgment.get('route')}",
            f"intent={judgment.get('intent')}",
            f"confidence={judgment.get('confidence')}",
        ]
        for key in ("city", "neighborhood", "genre", "date_phrase", "artist", "venue"):
            if judgment.get(key):
                bits.append(f"{key}={judgment.get(key)}")
        if judgment.get("reason"):
            bits.append(f"reason={judgment.get('reason')}")
        return "Router notes (hints only — still call tools; never invent shows): " + "; ".join(bits)


    def _as_dt(self, value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        text = str(value).replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _load_global_rules(self, phone_number):
        data = {}
        if self.get_conversation:
            result = self.get_conversation(phone_number) or {}
            data = result.get("data") or {}
        if not data:
            data = self._memory.get(phone_number) or {}
        return (data.get("global_rules") or "").strip()

    def _load_conversation(self, phone_number):
        data = {}
        if self.get_conversation:
            result = self.get_conversation(phone_number) or {}
            data = result.get("data") or {}
        if not data:
            data = self._memory.get(phone_number) or {}
        started_at = self._as_dt(data.get("started_at")) or datetime.now(timezone.utc)
        messages = list(data.get("messages") or [])
        global_rules = (data.get("global_rules") or "").strip()
        if len(messages) > STORE_SOFT_CAP:
            messages = messages[-STORE_SOFT_CAP:]
        is_new = len(messages) == 0
        return messages, started_at, is_new, global_rules

    def _persist_conversation(
        self,
        phone_number,
        messages,
        started_at,
        global_rules=None,
        update_rules=False,
    ):
        prior = self._memory.get(phone_number) or {}
        rules = (
            (global_rules or "")
            if update_rules or global_rules is not None
            else (prior.get("global_rules") or getattr(self, "_global_rules", "") or "")
        )
        payload = {
            "messages": messages,
            "started_at": started_at.isoformat() if hasattr(started_at, "isoformat") else started_at,
            "global_rules": rules,
        }
        self._memory[phone_number] = payload
        if self.save_conversation:
            try:
                self.save_conversation(
                    phone_number,
                    messages,
                    started_at,
                    global_rules=rules,
                )
            except TypeError:
                self.save_conversation(phone_number, messages, started_at)

    def _clear_conversation(self, phone_number):
        self._memory.pop(phone_number, None)
        if self.delete_conversation:
            self.delete_conversation(phone_number)

    def _openai_history(self, history):
        cleaned = []
        for item in history or []:
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            cleaned.append({"role": role, "content": item.get("content") or ""})
        return cleaned

    def _store_turn(self, phone_number, history, started_at, user_text, parts, artists=None, slots=None):
        history.append({"role": "user", "content": user_text})
        outbound = parts if isinstance(parts, (list, tuple)) else [parts]
        for index, part in enumerate(outbound):
            item = {"role": "assistant", "content": (part or "")[:MAX_SMS_CHARS]}
            if artists and index == len(outbound) - 1:
                item["spotify_artists"] = artists
            history.append(item)
        if slots is not None:
            public = filter_public_messages(history)
            history[:] = upsert_slots_message(public, slots)
        if len(history) > STORE_SOFT_CAP:
            slots_msg = [m for m in history if m.get("role") == SLOTS_ROLE]
            body = [m for m in history if m.get("role") != SLOTS_ROLE][-STORE_SOFT_CAP:]
            history[:] = body + slots_msg[-1:]
        self._persist_conversation(phone_number, history, started_at)

    def _with_intro(self, parts, is_new):
        raw = parts if isinstance(parts, (list, tuple)) else [parts]
        outbound = []
        for part in raw:
            outbound.extend(self._split_sms_parts(part))
        if not outbound:
            return "I didn't catch that. Try a city or genre?"
        if is_new:
            outbound[0] = self._gsm_safe_sms(f"{INTRO_MESSAGE}\n\n{outbound[0]}")
            # Intro can push past limit — re-split first bubble only.
            head = self._split_sms_parts(outbound[0])
            outbound = head + outbound[1:]
        return outbound if len(outbound) > 1 else outbound[0]

    def _pending_spotify_artists(self, history):
        for item in reversed(history or []):
            artists = [name for name in (item.get("spotify_artists") or []) if name]
            if artists:
                return artists
        return []

    def _looks_like_new_search(self, text):
        raw = text or ""
        if DATE_WORDS_RE.search(raw):
            return True
        if re.search(r"\b(in|near|around)\s+[a-z]", raw, re.I) and len(raw.split()) >= 3:
            return True
        if re.search(
            r"\b(shows?|events?|tickets?|artists?|djs?|gigs?|genre|genres|tagged|"
            r"who (can|should) i (see|go)|what (can|should) i (see|go))\b",
            raw,
            re.I,
        ):
            return True
        if re.search(r"\blike\s+\w+(\s+\w+)?\s+music\b", raw, re.I):
            return True
        lowered = raw.lower()
        for family, members in GENRE_FAMILIES.items():
            for name in (family, *members):
                if len(name) >= 4 and re.search(rf"\b{re.escape(name)}\b", lowered):
                    return True
        return False

    def _looks_like_artist_fact(self, text):
        return bool(re.search(
            r"\b(genre|genres|tagged|who('?s| is)|what('?s| is)|what kind|what style|"
            r"tell me about)\b",
            text or "",
            re.I,
        ))

    def _join_or(self, names):
        names = [name for name in names if name]
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} or {names[1]}"
        return f"{', '.join(names[:-1])}, or {names[-1]}"

    def _spotify_offer_text(self, artists):
        names = [name for name in (artists or []) if name][:3]
        if not names:
            return ""
        if len(names) == 1:
            return f"Want to check {names[0]} on Spotify? Reply yes."
        return f"Want any of these on Spotify? {self._join_or(names)}."

    def _spotify_which_text(self, artists):
        names = [name for name in (artists or []) if name][:3]
        if not names:
            return ""
        return f"Which one? {self._join_or(names)}."

    def _spotify_card_messages(self, artist):
        catalog = self._catalog_artist_card(artist)
        card = self.spotify.lookup_artist(artist) if getattr(self.spotify, "enabled", False) else {}
        sms = (card or {}).get("sms")
        if sms:
            self._spotify_card_sms = sms
            return [sms]
        if catalog and catalog.get("sms"):
            self._spotify_card_sms = catalog["sms"]
            return [catalog["sms"]]
        name = artist or "that artist"
        return [f"Spotify is paused right now. I still have {name} on the calendar if you want dates."]

    def _match_pending_artist(self, text, artists):
        cleaned = re.sub(r"[^a-z0-9:+]+", " ", (text or "").lower()).strip()
        cleaned = re.sub(r"\b(the|on|spotify|check|out|please|yes|yeah)\b", " ", cleaned)
        cleaned = " ".join(cleaned.split())
        if not cleaned:
            return None
        best = None
        best_score = 0.0
        for artist in artists or []:
            key = re.sub(r"[^a-z0-9:+]+", " ", artist.lower()).strip()
            if not key:
                continue
            if cleaned == key or key in cleaned or cleaned in key:
                return artist
            score = SequenceMatcher(None, cleaned, key).ratio()
            if score > best_score:
                best = artist
                best_score = score
        if best_score >= 0.72:
            return best
        return None

    def _try_spotify_followup(self, text, artists):
        artists = [name for name in (artists or []) if name][:3]
        if not artists:
            return None
        lowered = " ".join((text or "").strip().lower().split())
        if self._looks_like_artist_fact(text):
            return None
        if SPOTIFY_NO_RE.match(lowered):
            return ["All good."], None
        ordinal_key = re.sub(r"[^a-z0-9 ]+", "", lowered)
        if ordinal_key in SPOTIFY_ORDINALS:
            index = SPOTIFY_ORDINALS[ordinal_key]
            if index < len(artists):
                return self._spotify_card_messages(artists[index]), None
        matched = self._match_pending_artist(text, artists)
        if matched:
            return self._spotify_card_messages(matched), None
        if SPOTIFY_YES_RE.match(lowered) or lowered in {"spotify", "the songs", "a song"}:
            if len(artists) == 1:
                return self._spotify_card_messages(artists[0]), None
            which = self._spotify_which_text(artists)
            return ([which], artists) if which else None
        return None

    def _us_now(self):
        return datetime.now(US_TZ)

    def _clock(self):
        now = self._us_now()
        today = now.date()
        tomorrow = today + timedelta(days=1)
        weekday = today.weekday()
        if weekday >= 4:
            friday = today - timedelta(days=weekday - 4)
        else:
            friday = today + timedelta(days=4 - weekday)
        sunday = friday + timedelta(days=2)
        hour = now.strftime("%I").lstrip("0") or "12"
        return {
            "now_display": f"{now.strftime('%A, %B %d, %Y')}, {hour}:{now.strftime('%M %p')} Pacific",
            "today_long": today.strftime("%A, %B %d, %Y"),
            "today_iso": today.isoformat(),
            "today_slash": today.strftime("%Y/%m/%d"),
            "tomorrow_iso": tomorrow.isoformat(),
            "weekend": f"{friday.isoformat()} to {sunday.isoformat()}",
            "weekend_start": friday,
            "weekend_end": sunday,
            "today": today,
        }

    def _system_prompt(self, user, global_rules="", judgment=None, deep=False, constraints=None):
        profile = "No saved profile yet."
        if user:
            name = user.get("name") or "unknown"
            genres = ", ".join(user.get("genre_list") or []) or "none"
            profile = f"Name: {name}. Soft genre prefs: {genres}."
        clock = self._clock()
        rules = (global_rules or "").strip() or "None yet."
        parts = [
            SYSTEM_PROMPT.format(
                now_display=clock["now_display"],
                today_long=clock["today_long"],
                today_iso=clock["today_iso"],
                today_slash=clock["today_slash"],
                tomorrow_iso=clock["tomorrow_iso"],
                weekend=clock["weekend"],
            ),
            f"Current texter: {profile}",
            f"Global rules (durable taste/style):\n{rules}",
        ]
        notes = self._judgment_prompt_block(judgment)
        if notes:
            parts.append(notes)
        resolved = self._constraints_prompt_block(constraints)
        if resolved:
            parts.append(resolved)
        if deep:
            parts.append(DEEP_MODE_ADDENDUM.strip())
        return "\n\n".join(parts)

    def _format_transcript(self, messages, limit_chars=6000):
        lines = []
        total = 0
        for item in messages or []:
            role = item.get("role") or "?"
            content = (item.get("content") or "").strip()
            if not content:
                continue
            line = f"{role}: {content}"
            if total + len(line) + 1 > limit_chars:
                break
            lines.append(line)
            total += len(line) + 1
        return "\n".join(lines)

    def _compact_rules_text(self, existing_rules, older_messages):
        if not self._client:
            return (existing_rules or "").strip()
        excerpt = self._format_transcript(older_messages)
        if not excerpt.strip():
            return (existing_rules or "").strip()
        prompt = COMPACT_RULES_PROMPT.format(max_chars=MAX_RULES_CHARS)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"Existing rules:\n{(existing_rules or '').strip() or '(none)'}\n\n"
                        f"Conversation excerpt to fold in:\n{excerpt}"
                    ),
                },
            ],
            temperature=0.2,
        )
        text_out = ((response.choices[0].message.content or "") if response.choices else "").strip()
        if not text_out:
            return (existing_rules or "").strip()
        return text_out[:MAX_RULES_CHARS]

    def compact_conversations(self, keep=PROMPT_WINDOW, min_extra=COMPACT_MIN_EXTRA):
        """Daily job: fold older turns into global_rules, then trim the message window."""
        rows = []
        if self.list_conversations:
            result = self.list_conversations() or {}
            if isinstance(result, dict):
                rows = result.get("data") or []
            elif isinstance(result, list):
                rows = result
        stats = {"scanned": 0, "compacted": 0, "skipped": 0, "errors": 0}
        for row in rows:
            stats["scanned"] += 1
            phone = row.get("phone_number")
            messages = list(row.get("messages") or [])
            if not phone:
                stats["skipped"] += 1
                continue
            if len(messages) <= keep + min_extra:
                stats["skipped"] += 1
                continue
            older = messages[:-keep]
            recent = messages[-keep:]
            try:
                new_rules = self._compact_rules_text(row.get("global_rules") or "", older)
                started_at = self._as_dt(row.get("started_at")) or datetime.now(timezone.utc)
                self._persist_conversation(
                    phone,
                    recent,
                    started_at,
                    global_rules=new_rules,
                    update_rules=True,
                )
                stats["compacted"] += 1
            except Exception:
                stats["errors"] += 1
                logger.exception("SMS compact failed for %s", str(phone)[-4:])
        return stats

    def _event_date(self, event):
        text = f"{event.get('raw_date') or ''} {event.get('date') or ''}"
        return self._parse_day(text)

    def _parse_day(self, value, default_year=None):
        if not value:
            return None
        text = str(value).strip()
        match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None
        year = default_year or self._clock()["today"].year
        named = re.search(
            r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
            r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
            r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b",
            text,
            re.I,
        )
        if named:
            month = MONTHS.get(named.group(1).lower())
            try:
                parsed = date(year, month, int(named.group(2)))
            except (TypeError, ValueError):
                return None
            today = self._clock()["today"]
            if parsed < today - timedelta(days=14):
                try:
                    parsed = date(year + 1, month, int(named.group(2)))
                except ValueError:
                    return parsed
            return parsed
        return None

    def _next_weekday(self, weekday, today=None):
        today = today or self._clock()["today"]
        return today + timedelta(days=(weekday - today.weekday()) % 7)

    def _parse_date_window(self, value):
        if value is None or value == "":
            return None, None
        if isinstance(value, date):
            return value, value
        text = str(value).strip()
        if not text:
            return None, None
        clock = self._clock()
        today = clock["today"]
        lowered = text.lower()
        if re.search(r"\b(tonight|today|this evening)\b", lowered):
            return today, today
        if re.search(r"\btomorrow\b", lowered):
            day = today + timedelta(days=1)
            return day, day
        in_days = re.search(r"\bin\s+(\d+)\s+days?\b", lowered)
        if in_days:
            day = today + timedelta(days=int(in_days.group(1)))
            return day, day
        if re.search(r"\bthis weekend\b", lowered):
            start = max(today, clock["weekend_start"])
            end = clock["weekend_end"]
            if start > end:
                start = clock["weekend_start"] + timedelta(days=7)
                end = clock["weekend_end"] + timedelta(days=7)
            return start, end
        if re.search(r"\bnext weekend\b", lowered):
            # Coming Fri–Sun after the current calendar weekend's Friday.
            start = clock["weekend_start"] + timedelta(days=7)
            end = clock["weekend_end"] + timedelta(days=7)
            return start, end
        if re.search(r"\bnext week\b", lowered):
            # Tomorrow through end of next calendar week (Sunday).
            start = today + timedelta(days=1)
            # Next week's Sunday: days until Sunday, then +7 if today is Sunday
            days_until_sunday = (6 - today.weekday()) % 7
            this_sunday = today + timedelta(days=days_until_sunday)
            end = this_sunday + timedelta(days=7)
            if start > end:
                end = start + timedelta(days=6)
            return start, end
        if re.search(r"\bthis week\b", lowered):
            end = today + timedelta(days=(6 - today.weekday()))
            return today, end
        span = re.search(
            r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})\s*(?:to|-|–|through)\s*(20\d{2}[-/]\d{1,2}[-/]\d{1,2})",
            lowered,
        )
        if span:
            start = self._parse_day(span.group(1))
            end = self._parse_day(span.group(2))
            if start and end:
                return (start, end) if start <= end else (end, start)
        wants_next = bool(re.search(r"\bnext\b", lowered))
        for name, index in WEEKDAYS.items():
            if re.search(rf"\b{name}s?\b", lowered):
                day = self._next_weekday(index, today)
                if wants_next and day == today:
                    day += timedelta(days=7)
                return day, day
        parsed = self._parse_day(text)
        if parsed:
            return parsed, parsed
        return None, None

    def _human_window(self, start, end):
        if not start:
            return None
        if not end or start == end:
            return self._human_day(start)
        return f"{self._human_day(start)}–{self._human_day(end)}"

    def _in_date_window(self, event_day, start, end):
        if not start or not event_day:
            return False
        close = end or start
        return start <= event_day <= close

    def _message_names_a_day(self, text):
        return bool(DATE_WORDS_RE.search(text or ""))

    def _city_needle(self, city):
        raw = " ".join(str(city or "").replace(",", " ").replace("/", " ").lower().split())
        if not raw:
            return ""
        return CITY_ALIASES.get(raw, raw)

    def _peel_city_from_query(self, query, city=None):
        """If the model stuffed a city into q (e.g. 'bassvictim seattle'), split it out."""
        text = " ".join(str(query or "").split()).strip()
        if not text:
            return None, city
        phrases = sorted({
            *CITY_ALIASES.keys(),
            *CITY_ALIASES.values(),
            "seattle", "denver", "austin", "miami", "atlanta", "boston",
            "dallas", "houston", "chicago", "oakland", "san diego", "san jose",
            "phoenix", "las vegas", "vegas", "boulder", "vancouver", "detroit",
            "philadelphia", "toronto", "brooklyn",
        }, key=len, reverse=True)
        found = None
        cleaned = text
        for phrase in phrases:
            if not phrase or len(phrase) < 2:
                continue
            pat = rf"(?:^|[\s,|/]+|(?<=\s)in\s+)({re.escape(phrase)})(?:$|[\s,|/]+)"
            match = re.search(pat, cleaned, re.I)
            if not match:
                # also plain token
                match = re.search(rf"\b{re.escape(phrase)}\b", cleaned, re.I)
            if not match:
                continue
            found = CITY_ALIASES.get(phrase.lower(), phrase.lower())
            cleaned = (cleaned[:match.start()] + " " + cleaned[match.end():]).strip()
            cleaned = re.sub(r"\b(in|at|near|around|for)\b", " ", cleaned, flags=re.I)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,|/")
            break
        if found and not city:
            city = found.title() if found not in CITY_ALIASES.values() else found
            # keep canonical lower-ish names for needle; title is fine for display
            city = found
        return (cleaned or None), city


    _NEIGHBORHOOD_JSON_SHAPE = (
        '{"neighborhood":"<canonical name>","city":"<city>",'
        '"venues":["<exact venue string from input>", "..."],'
        '"confidence":"high|medium|low"}'
    )

    def _neighborhood_cache_key(self, city, neighborhood):
        return (
            " ".join(str(city or "").lower().split()),
            " ".join(str(neighborhood or "").lower().split()),
        )

    def _peel_neighborhood(self, text, city=None):
        """Pull a neighborhood/area phrase out of free text. Returns (cleaned, neighborhood)."""
        raw = " ".join(str(text or "").split()).strip()
        if not raw:
            return None, None
        city_l = " ".join(str(city or "").lower().replace(",", " ").split())
        patterns = [
            r"capitol\s*hill",
            r"beacon\s*hill",
            r"queen\s*anne",
            r"university\s*district",
            r"u\.?\s*district",
            r"international\s*district",
            r"central\s*district",
            r"pike\s*/?\s*pine",
            r"williamsburg",
            r"bushwick",
            r"greenpoint",
            r"east\s*village",
            r"west\s*hollywood",
            r"silver\s*lake",
            r"echo\s*park",
            r"mission\s*district",
            r"soma",
            r"soho",
            r"dumbo",
            r"ballard",
            r"fremont",
            r"georgetown",
            r"belltown",
            r"sodo",
            r"downtown",
            r"midtown",
            r"chinatown",
            r"brooklyn",
            r"hollywood",
        ]
        for pat in patterns:
            match = re.search(rf"\b({pat})\b", raw, re.I)
            if not match:
                continue
            phrase = re.sub(r"\s+", " ", match.group(1)).strip()
            if city_l and phrase.lower() == city_l:
                continue
            cleaned = (raw[:match.start()] + " " + raw[match.end():]).strip()
            cleaned = re.sub(r"\b(in|at|near|around|area|neighborhood|district)\b", " ", cleaned, flags=re.I)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,|/")
            if phrase.lower() == "sodo":
                return (cleaned or None), "SoDo"
            return (cleaned or None), phrase.title()
        match = re.search(
            r"\b(?:in|near|around)\s+([a-z0-9][a-z0-9\s/.'-]{1,40}?)"
            r"(?:\s+(?:area|neighborhood|district|side))?\b",
            raw,
            re.I,
        )
        if match:
            phrase = re.sub(r"\s+", " ", match.group(1)).strip(" ,.")
            phrase_l = phrase.lower()
            # Reject numeric crumbs ("in 2 days") and date leftovers
            if phrase_l.isdigit() or re.match(r"^\d+\s*days?$", phrase_l):
                return raw, None
            if len(phrase_l) < 3:
                return raw, None
            if phrase_l and phrase_l != city_l and phrase_l not in {
                "the", "my", "this", "that", "town", "city", "shows", "events",
                "house", "techno", "bass", "trance", "dubstep", "hardstyle",
            }:
                cleaned = (raw[:match.start()] + " " + raw[match.end():]).strip()
                cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,|/")
                return (cleaned or None), phrase.title()
        return raw, None

    def _unique_event_venues(self, events, limit=220):
        seen = []
        seen_l = set()
        for event in events or []:
            venue = (event.get("venue") or "").strip()
            if not venue:
                continue
            key = venue.lower()
            if key in seen_l:
                continue
            seen_l.add(key)
            seen.append(venue)
            if len(seen) >= limit:
                break
        return seen

    def _match_neighborhood_venues(self, city, neighborhood, venues):
        """
        LLM venue filter. Expected JSON shape:
          {"neighborhood": str, "city": str, "venues": [exact input strings...], "confidence": "high"|"medium"|"low"}
        Cached per (city, neighborhood).
        """
        city = (city or "").strip()
        neighborhood = (neighborhood or "").strip()
        venues = [v for v in (venues or []) if v]
        if not city or not neighborhood or not venues:
            return []

        cache_key = self._neighborhood_cache_key(city, neighborhood)
        cached = self._neighborhood_cache.get(cache_key)
        if cached is not None:
            allowed = {v.lower() for v in cached}
            return [v for v in venues if v.lower() in allowed]

        if not self._client:
            return []

        venue_block = "\n".join(f"- {venue}" for venue in venues)
        system = (
            "You map music venues to city neighborhoods for an event search filter. "
            "Reply with ONE JSON object only, no markdown, matching this shape exactly:\n"
            f"{self._NEIGHBORHOOD_JSON_SHAPE}\n"
            "Rules:\n"
            "- `venues` must be a subset of the provided venue strings, copied EXACTLY (same spelling/punctuation).\n"
            "- Include a venue if it is in the neighborhood OR immediately adjacent / commonly treated as that area.\n"
            "- If unsure, omit the venue. Prefer precision over recall.\n"
            "- Never invent venue names that were not listed.\n"
            "- `confidence` is your overall confidence for the set."
        )
        user = (
            f"City: {city}\n"
            f"Neighborhood / area query: {neighborhood}\n"
            f"Venues ({len(venues)}):\n{venue_block}"
        )
        try:
            response = self._chat_completion(
                model=os.environ.get("OPENAI_NEIGHBORHOOD_MODEL") or self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=0,
                max_tokens=900,
            )
            raw_out = (response.choices[0].message.content or "").strip()
            payload = json.loads(raw_out) if raw_out else {}
        except Exception:
            logger.exception("neighborhood venue match failed for %s / %s", city, neighborhood)
            return []

        matched = []
        allowed_input = {v.lower(): v for v in venues}
        for item in payload.get("venues") or []:
            key = str(item or "").strip().lower()
            if key in allowed_input:
                matched.append(allowed_input[key])
        self._neighborhood_cache[cache_key] = matched
        logger.info(
            "neighborhood match %s/%s -> %s venues (confidence=%s)",
            city,
            neighborhood,
            len(matched),
            payload.get("confidence"),
        )
        return matched

    def _event_in_venues(self, event, venues):
        if not venues:
            return False
        venue = (event.get("venue") or "").strip().lower()
        if not venue:
            return False
        allowed = {v.strip().lower() for v in venues}
        if venue in allowed:
            return True
        short = re.sub(r"\s*\([^)]*\)\s*$", "", venue).strip()
        shorts = {re.sub(r"\s*\([^)]*\)\s*$", "", v).strip().lower() for v in venues}
        return bool(short and short in shorts)

    def _city_hit(self, event, city_l):
        needle = self._city_needle(city_l)
        if not needle:
            return True
        venue = (event.get("venue") or "").lower().replace(",", " ")
        city = (event.get("city") or "").lower().replace(",", " ")
        paren = re.search(r"\(([^)]+)\)", venue)
        places = []
        if city:
            places.append(self._city_needle(city))
        if paren:
            places.append(self._city_needle(paren.group(1)))
        for place in places:
            if place and (place == needle or needle in place):
                return True
        return bool(re.search(rf"\b{re.escape(needle)}\b", venue))

    def _human_day(self, value):
        if isinstance(value, date):
            return f"{value.strftime('%a')} {value.month}/{value.day}"
        parsed = self._parse_day(value) if value else None
        if parsed:
            return f"{parsed.strftime('%a')} {parsed.month}/{parsed.day}"
        return (str(value).strip() if value else "") or None

    def _sms_title(self, name):
        name = (name or "Untitled show").strip()
        if ":" in name and (len(name) > 72 or name.count(",") >= 2):
            head = name.split(":", 1)[0].strip()
            if head:
                name = head
        if len(name) <= 72:
            return name
        return name[:69].rstrip(" ,;:-") + "..."

    def _sms_venue(self, venue):
        text = (venue or "").strip()
        if not text:
            return ""
        cut = re.search(r"\s*\(", text)
        if cut:
            text = text[:cut.start()].strip()
        text = re.split(
            r"(?:\$\s*\d|20\d{2}\s*/|\b(?:facebook|instagram|ticketweb)\b)",
            text,
            maxsplit=1,
            flags=re.I,
        )[0]
        return re.sub(r"\s+", " ", text).strip(" ,;-|")

    def _sms_price_line(self, ticket_info):
        text = (ticket_info or "").strip()
        if not text or text.upper() in {"N/A", "NA", "NONE", "-"}:
            return ""
        parts = [re.sub(r"\s+", " ", part).strip() for part in re.split(r"\s*\|\s*", text)]
        bits = []
        age = ""
        for part in parts:
            if not part:
                continue
            lowered = part.lower()
            if lowered in {"all ages", "all-ages", "allages"}:
                continue
            if re.fullmatch(r"\d{2}\+", part):
                age = part
                continue
            bits.append(part)
        joined = " / ".join(bits)
        if not age:
            match = re.search(r"\b(\d{2}\+)\b", joined)
            if match:
                age = match.group(1)
                joined = re.sub(r"\s*\b\d{2}\+\b", "", joined).strip(" /")
        messy = bool(re.search(r"\bb4\b|/|w/rsvp|notaflof", joined, re.I))
        if len(joined) > 18 or messy:
            if re.search(r"\bfree\b", joined, re.I):
                joined = "free"
            else:
                amounts = re.findall(r"\$\s*\d+", joined)
                if amounts:
                    joined = amounts[0].replace(" ", "")
                    if "+" in (ticket_info or "") or "-" in (ticket_info or ""):
                        joined += "+"
                else:
                    joined = ""
        return " | ".join(part for part in (joined, age) if part)

    def _format_sms_show(self, event):
        when = self._human_day(self._event_date(event)) or (event.get("date") or "").strip() or "TBA"
        name = self._sms_title(event.get("event_name") or "Untitled show")
        venue = self._sms_venue(event.get("venue") or "")
        city = (event.get("city") or "").strip()
        if city and city.lower() not in venue.lower():
            venue = ", ".join(part for part in (venue, city) if part)
        price = self._sms_price_line(event.get("ticket_info") or "")
        station = (event.get("_transit_station") or "").strip()
        miles = event.get("_transit_miles")
        origin_stop = (event.get("_transit_origin") or "").strip()
        if station:
            rail = "MAX" if "portland" in (city or "").lower() else "Link"
            if origin_stop and origin_stop.lower() != station.lower():
                walk = f", ~{miles} mi walk" if miles is not None else ""
                venue = f"{venue} ({rail}: {origin_stop} -> {station}{walk})"
            elif miles is not None:
                venue = f"{venue} ({rail}: {station}, ~{miles} mi)"
            else:
                venue = f"{venue} ({rail}: {station})"
        headline = f"{when}: {name}"
        detail = ", ".join(part for part in (venue, price) if part)
        lines = [headline]
        if detail:
            lines.append(detail)
        url = self._sms_url(event.get("event_url") or "")
        if url:
            lines.append(url)
        return "\n".join(lines)

    def _sms_url(self, url):
        """SMS-safe URL: strip tracking junk that blows past carrier size limits."""
        cleaned = clean_event_url(url or "")
        if not cleaned:
            return ""
        parsed = urlparse(cleaned.strip())
        # Drop query/fragment entirely for SMS — etix/_ga blobs trigger Twilio 30019.
        if parsed.scheme and parsed.netloc:
            path = parsed.path or ""
            return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
        return cleaned.split("?", 1)[0].split("#", 1)[0]

    def _gsm_safe_sms(self, text):
        """Prefer GSM-7 so carriers don't UCS-2-inflate segment size."""
        if not text:
            return ""
        out = (
            str(text)
            .replace("\u2014", "-")
            .replace("\u2013", "-")
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2026", "...")
            .replace("\u00a0", " ")
        )
        return out

    def _split_sms_parts(self, text, limit=SMS_PART_CHARS):
        """Split one long reply into carrier-safe Twilio messages."""
        text = self._gsm_safe_sms(text or "").strip()
        if not text:
            return ["I didn't catch that. Try a city or genre?"]
        if len(text) <= limit:
            return [text]

        # Prefer blank-line / show-card boundaries.
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b and b.strip()]
        parts = []
        current = ""

        def flush():
            nonlocal current
            if current.strip():
                parts.append(current.strip())
            current = ""

        def push_chunk(chunk):
            nonlocal current
            chunk = chunk.strip()
            if not chunk:
                return
            if len(chunk) <= limit:
                candidate = f"{current}\n\n{chunk}".strip() if current else chunk
                if len(candidate) <= limit:
                    current = candidate
                else:
                    flush()
                    current = chunk
                return
            # Hard-wrap oversized block (usually a long opener).
            flush()
            words = chunk.split()
            buf = ""
            for word in words:
                trial = f"{buf} {word}".strip() if buf else word
                if len(trial) <= limit:
                    buf = trial
                else:
                    if buf:
                        parts.append(buf)
                    buf = word if len(word) <= limit else word[: limit - 1] + "…"
            if buf:
                current = buf

        for block in blocks or [text]:
            push_chunk(block)
        flush()
        return parts[:6] or [text[:limit]]

    def _clip_at_sentence(self, text, limit=MAX_SMS_CHARS):
        text = re.sub(r"\s+", " ", (text or "")).strip()
        if len(text) <= limit:
            return text
        chunk = text[:limit].rstrip()
        for sep in (". ", "! ", "? "):
            idx = chunk.rfind(sep)
            if idx >= min(80, limit // 3):
                return chunk[: idx + 1].strip()
        clipped = chunk.rsplit(" ", 1)[0].rstrip(".,;:")
        return clipped or chunk

    def _venue_blurb(self, place):
        name = self._sms_venue(place.get("display_name") or place.get("venue") or "That room")
        try:
            rating = float(place.get("rating") or 0)
        except (TypeError, ValueError):
            rating = 0.0
        try:
            count = int(place.get("user_rating_count") or 0)
        except (TypeError, ValueError):
            count = 0
        if rating and count:
            head = f"{name} is {rating:g} stars from {count:,} Google reviews."
        elif rating:
            head = f"{name} is {rating:g} stars on Google."
        else:
            head = f"{name}."
        summary = (place.get("review_summary") or place.get("editorial_summary") or "").strip()
        if summary:
            return self._clip_at_sentence(f"{head} {summary}")
        reviews = place.get("reviews") or []
        snippets = []
        for item in reviews[:2]:
            bit = re.sub(r"\s+", " ", (item.get("text") or "")).strip()
            if bit:
                snippets.append(bit)
        if snippets:
            return self._clip_at_sentence(f"{head} {' '.join(snippets)}")
        return head + " I don't have a Google writeup beyond the rating."

    def _venue_rank_line(self, place):
        name = self._sms_venue(place.get("display_name") or place.get("venue") or "That room")
        try:
            rating = float(place.get("rating") or 0)
        except (TypeError, ValueError):
            rating = 0.0
        try:
            count = int(place.get("user_rating_count") or 0)
        except (TypeError, ValueError):
            count = 0
        if rating and count:
            return f"{name} — {rating:g} from {count:,} Google reviews"
        if rating:
            return f"{name} — {rating:g} on Google"
        return name

    def _rank_venues_card(self, city, limit=3):
        city = (city or "").strip()
        if not city:
            return {"error": "missing_city", "sms": "Which city? Try Seattle, Portland, or LA."}
        rooms = rank_places(self._venue_index(), city, limit=limit)
        if not rooms:
            return {
                "error": "not_found",
                "city": city,
                "sms": f"I don't have ranked Google rooms for {city} yet.",
            }
        lines = [f"Top {city} rooms (Google):"]
        lines.extend(self._venue_rank_line(place) for place in rooms)
        lines.append("Name one for more.")
        return {
            "city": city,
            "venues": [
                {
                    "venue": place.get("display_name") or place.get("venue"),
                    "rating": place.get("rating"),
                    "user_rating_count": place.get("user_rating_count"),
                }
                for place in rooms
            ],
            "sms": "\n".join(lines),
        }

    def _try_venue_rank(self, text, history):
        raw = (text or "").strip()
        if not raw:
            return None
        follow = bool(VENUE_RANK_FOLLOW_RE.match(raw))
        if not follow and not VENUE_RANK_RE.search(raw):
            return None
        if self._looks_like_new_search(raw):
            return None
        city = self._guess_city(raw, history)
        for name in self._recent_venues(history):
            key = name.lower()
            if key in {"seattle", "portland"}:
                continue
            if re.search(rf"\b{re.escape(key)}\b", raw, re.I) and key not in city.lower():
                return None
        if not city:
            return "Which city? Try Seattle, Portland, or LA."
        card = self._rank_venues_card(city)
        return (card or {}).get("sms")

    def _lookup_venue_card(self, venue, city=""):
        venue = (venue or "").strip()
        if not venue:
            return {"error": "missing_venue"}
        index = self._venue_index()
        place = match_place(index, venue, city)
        if not place and city:
            place = match_place(index, venue, "")
        if not place:
            try:
                from services.venue_places import search_place
            except ImportError:
                from venue_places import search_place
            found = search_place(
                " ".join(part for part in (venue, city) if part),
                venue_name=venue,
                city=city,
            )
            if found.get("place_id"):
                place = found
                self._remember_place(venue, city, found)
        if not place:
            return {"error": "not_found", "venue": venue, "sms": f"I don't have Google notes on {venue}."}
        sms = self._venue_blurb(place)
        return {
            "venue": place.get("display_name") or venue,
            "city": place.get("city"),
            "rating": place.get("rating"),
            "user_rating_count": place.get("user_rating_count"),
            "sms": sms,
        }

    def _remember_place(self, venue, city, place):
        if not self.save_venue_place or not place or not place.get("place_id"):
            return
        row = place_cache_row(venue, city, place)
        if not row:
            return
        try:
            self.save_venue_place(row)
            self._place_index = None
        except Exception as exc:
            logger.warning("venue place save failed: %s", exc)

    def _recent_venues(self, history):
        names = []
        for item in reversed(history or []):
            if item.get("role") != "assistant":
                continue
            for line in (item.get("content") or "").splitlines():
                line = line.strip()
                if not line or "http" in line.lower():
                    continue
                if re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", line, re.I):
                    continue
                if re.match(r"^(want |listen:|sproutme |i don't have)", line, re.I):
                    continue
                if len(line) > 60:
                    continue
                name = self._sms_venue(line.split(",")[0])
                if 2 <= len(name) <= 48:
                    names.append(name)
            if names:
                return names[:8]
        return []

    def _guess_city(self, text, history):
        items = [{"content": text or ""}]
        items.extend(reversed(list(history or [])[-8:]))
        cities = (
            "los angeles", "san francisco", "san diego", "las vegas", "new york",
            "seattle", "portland", "denver", "oakland", "chicago", "detroit",
            "atlanta", "miami", "austin", "dallas", "houston", "phoenix",
            "boston", "vancouver", "brooklyn",
        )
        for item in items:
            blob = (item.get("content") or "").lower()
            for city in cities:
                if re.search(rf"\b{re.escape(city)}\b", blob):
                    return "Los Angeles" if city == "los angeles" else city.title()
        return ""

    def _venue_query_from_text(self, text, history):
        raw = (text or "").strip()
        if not raw:
            return None
        if self._looks_like_new_search(raw):
            return None
        recent = self._recent_venues(history)
        lowered = raw.lower()
        if re.fullmatch(r"(what (are|about) )?(the )?reviews?\??", lowered):
            return recent[0] if recent else None
        best = None
        for name in recent:
            key = name.lower()
            if key in lowered or re.search(rf"\b{re.escape(key)}\b", lowered):
                if not best or len(name) > len(best):
                    best = name
            first = key.split()[0]
            if first not in {"the", "a", "an"} and re.search(rf"\b{re.escape(first)}\b", lowered):
                if not best or len(name) >= len(best):
                    best = name
        if best:
            return best
        match = re.search(r"(?:how'?s|how is|what about)\s+(.+?)[\?!.]*$", raw, re.I)
        if match:
            return self._sms_venue(match.group(1))
        match = re.search(r"^is\s+(.+?)\s+(?:a |an )?(?:good|cool|worth)", raw, re.I)
        if match:
            return self._sms_venue(match.group(1))
        return None

    def _looks_like_stop_question(self, text):
        raw = (text or "").strip()
        if not raw:
            return False
        return bool(re.search(
            r"\b((which|what|nearest|closest)\s+(light\s*rail\s+|link\s+|train\s+|transit\s+)?stops?"
            r"|what\s+stop|which\s+stop|light\s*rail\s+stop|link\s+stop"
            r"|get off( at)?|station for)\b",
            raw,
            re.I,
        ))

    def _venue_from_stop_question(self, text, history):
        raw = (text or "").strip()
        match = re.search(
            r"(?:stop|station)\s+(?:for|at|near|by)\s+(.+?)[\?!.]*$",
            raw,
            re.I,
        )
        if match:
            return self._sms_venue(match.group(1))
        match = re.search(
            r"(?:for|at)\s+([A-Za-z0-9][A-Za-z0-9'&.\-\s]{1,40})[\?!.]*$",
            raw,
            re.I,
        )
        if match and not re.search(r"\b(stop|station|rail|link|tonight|weekend)\b", match.group(1), re.I):
            return self._sms_venue(match.group(1))
        return self._venue_query_from_text(raw, history)

    def _nearest_link_for_venue(self, venue, city=""):
        city = (city or "").strip() or "Seattle"
        place = match_place(self._venue_index(), venue, city) or match_place(self._venue_index(), venue, "")
        if not place or place.get("lat") is None or place.get("lng") is None:
            return None, None, None
        try:
            from services.neighborhoods import nearest_transit_station, transit_stations_for_city
        except ImportError:
            from neighborhoods import nearest_transit_station, transit_stations_for_city
        stations = transit_stations_for_city(city) or transit_stations_for_city("Seattle")
        hit = nearest_transit_station(place.get("lat"), place.get("lng"), city=city, stations=stations)
        if not hit:
            return place, None, None
        miles, station = hit
        return place, station, miles

    def _try_transit_stop_answer(self, text, history):
        """Answer 'what stop for Vice?' from recent recs + venue coords — not a show search."""
        if not self._looks_like_stop_question(text):
            return None
        venue = self._venue_from_stop_question(text, history)
        if not venue:
            recent = self._recent_venues(history)
            venue = recent[0] if recent else None
        if not venue:
            return "Which venue — I can tell you the closest Link stop."
        city = self._guess_city(text, history) or "Seattle"
        place, station, miles = self._nearest_link_for_venue(venue, city)
        display = self._sms_venue((place or {}).get("display_name") or venue)
        if not station:
            return f"I don't have a solid Link stop pinned for {display} yet."
        walk = f" (~{miles:.1f} mi walk)" if miles is not None else ""
        return f"For {display}, get off at {station} Station{walk}."

    def _try_venue_followup(self, text, history):
        if not VENUE_ASK_RE.search(text or ""):
            return None
        if self._looks_like_new_search(text):
            return None
        query = self._venue_query_from_text(text, history)
        if not query:
            return None
        card = self._lookup_venue_card(query, self._guess_city(text, history))
        return (card or {}).get("sms")

    def _join_show_blocks(self, blocks):
        return "\n\n".join(block.strip() for block in blocks if block and block.strip())

    def _is_show_followup(self, text):
        raw = (text or "").strip()
        if not raw or self._message_names_a_day(raw):
            return False
        if VENUE_ASK_RE.search(raw) or VENUE_RANK_RE.search(raw):
            return False
        return bool(re.search(
            r"\b(shows?|events?|lineup|playing|who'?s on|what'?s on|are there|going on|who'?s playing)\b",
            raw,
            re.I,
        ))

    def _date_from_recent_history(self):
        for item in reversed(self._conversation_history or []):
            if item.get("role") != "user":
                continue
            start, end = self._parse_date_window(item.get("content") or "")
            if start:
                return start, end
        return None, None

    def _catalog_venue_match(self, text):
        needle = re.sub(r"\s+", " ", (text or "").strip().lower())
        if len(needle) < 2:
            return None
        best = None
        for event in self._all_events() or []:
            venue = self._sms_venue(event.get("venue") or "")
            if not venue:
                continue
            key = venue.lower()
            if key == needle or needle in key or key in needle:
                if not best or len(venue) <= len(best):
                    best = venue
                continue
            if re.search(rf"\b{re.escape(needle)}\b", key) or re.search(rf"\b{re.escape(key)}\b", needle):
                if not best or len(venue) <= len(best):
                    best = venue
        return best

    def _try_bare_venue_lineup(self, phone_number, text, history):
        """Bare venue name → tonight/upcoming lineup, not a Google review."""
        raw = (text or "").strip()
        if not raw or len(raw) > 48 or len(raw.split()) > 5:
            return None
        if self._looks_like_stop_question(raw):
            return None
        if VENUE_ASK_RE.search(raw) or VENUE_RANK_RE.search(raw):
            return None
        if self._looks_like_new_search(raw) and not re.fullmatch(
            r".*\b(nightclub|club|lounge|ballroom|theater|theatre|hall|warehouse|basement)\b.*",
            raw,
            re.I,
        ):
            return None
        city = self._guess_city(raw, history)
        place = match_place(self._venue_index(), raw, city) or match_place(self._venue_index(), raw, "")
        venue_name = None
        if place and place.get("place_id"):
            venue_name = self._sms_venue(place.get("display_name") or place.get("venue") or raw)
        if not venue_name:
            venue_name = self._catalog_venue_match(raw)
        if not venue_name:
            return None
        args = {"q": venue_name, "limit": 5}
        if city:
            args["city"] = city
        hist_start, _hist_end = self._date_from_recent_history()
        if hist_start:
            args["date"] = hist_start.isoformat()
            # Force date application even though this message may not name a day.
            self._force_date_from_history = True
        try:
            result = self._search_for_texter(phone_number, args)
        finally:
            self._force_date_from_history = False
        pack = self._last_sms_pack or {}
        if not (pack.get("shows") or pack.get("later")):
            return None
        opener = ""
        if pack.get("wanted_day") and pack.get("shows"):
            opener = f"At {venue_name}:"
        elif pack.get("later") and not pack.get("shows"):
            opener = f"Nothing that night at {venue_name}. Next up:"
        else:
            opener = f"Upcoming at {venue_name}:"
        pack = {**pack, "opener": opener, "place": venue_name}
        self._last_sms_pack = pack
        return self._compose_sms_reply(opener, pack)

    def _compose_sms_reply(self, model_text, pack):
        pack = pack or {}
        shows = pack.get("shows") or []
        later = pack.get("later") or []
        place = pack.get("place") or "that city"
        deep = bool(getattr(self, "_deep_mode", False) or pack.get("deep"))
        if not shows and not later:
            return (model_text or "").strip() or f"No matching shows found in {place}."

        # Deep replies should speak to the ask — don't default to ranked "Best X I have" fluff.
        opener = "" if deep else (pack.get("opener") or "").strip()
        if model_text:
            lines = [line.strip() for line in model_text.strip().splitlines() if line.strip()]
            spoken = []
            for line in lines:
                looks_like_show = bool(re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", line, re.I))
                labeled = bool(re.match(r"^(biggest name|best room|heating up|soonest)\b", line, re.I))
                meh_rank = bool(re.match(r"^best .+ i have [—-]", line, re.I))
                fluff = bool(re.match(
                    r"^(here are|here's|a few|some |try these|found |i found|check these|listen:|want to check|want any)\b",
                    line,
                    re.I,
                ))
                blocked = any(line and line in block for block in shows + later)
                if looks_like_show or labeled or fluff or blocked or meh_rank or "http" in line.lower():
                    break
                spoken.append(line.rstrip(":"))
                if not deep or len(spoken) >= 2:
                    break
            if spoken:
                joined = "\n".join(spoken) if deep else spoken[0]
                max_len = 280 if deep else 160
                if 12 <= len(joined) <= max_len:
                    opener = joined

        if shows:
            body = self._join_show_blocks(shows[:2])
            if later and pack.get("wanted_day") and len(shows) < 2:
                body = f"{body}\n\nNext:\n{later[0]}"
        else:
            if not deep:
                opener = ""
            body = f"Nothing that night in {place}."
            if later:
                body = f"{body}\n\nNext:\n{self._join_show_blocks(later[:2])}"

        if opener:
            return f"{opener}\n\n{body}"
        return body

    def _drop_past_events(self, events, today, requested_date=None):
        keep_past = False
        wanted = self._parse_day(requested_date) if requested_date else None
        if wanted is not None and wanted < today:
            keep_past = True
        if keep_past:
            return events
        kept = []
        for event in events:
            event_day = self._event_date(event)
            if event_day is not None and event_day < today:
                continue
            kept.append(event)
        return kept

    def _clean_label(self, value):
        if not isinstance(value, str):
            return ""
        return value.strip().strip('"').strip("'").strip()

    def _clean_list(self, values):
        return [item for item in (self._clean_label(value) for value in (values or [])) if item]

    def _norm_genre(self, value):
        text = self._clean_label(value).lower().replace("&", " and ").replace("-", " ")
        return re.sub(r"\s+", " ", text).strip()

    def _genre_stems(self, label):
        key = self._norm_genre(label)
        if not key:
            return set()
        stems = {key}
        if key.endswith("es") and len(key) > 4:
            stems.add(key[:-2])
        if key.endswith("s") and not key.endswith("ss") and len(key) > 3:
            stems.add(key[:-1])
        return stems

    def _expand_genre(self, label):
        stems = self._genre_stems(label)
        key = self._norm_genre(label)
        tags = set(stems)
        if not key:
            return tags
        for family, members in GENRE_FAMILIES.items():
            names = {self._norm_genre(family), *[self._norm_genre(member) for member in members]}
            if key in names or stems & names:
                matched = True
            else:
                matched = any(
                    name
                    and abs(len(key) - len(name)) <= 2
                    and self._close_token(key, name)
                    for name in names
                )
            if matched:
                tags.update(names)
                for name in list(names):
                    tags.update(self._genre_stems(name))
        return tags

    def _genre_hit(self, event, wanted_labels):
        if not wanted_labels:
            return False
        event_text = self._norm_genre(event.get("genre") or "")
        if not event_text:
            return False
        event_tags = set()
        for part in re.split(r"[,/;|]+", event_text):
            event_tags.update(self._expand_genre(part))
        wanted = set()
        for label in wanted_labels:
            wanted.update(self._expand_genre(label))
        return bool(event_tags & wanted)

    def _close_token(self, left, right):
        if not left or not right:
            return False
        if left == right:
            return True
        if min(len(left), len(right)) >= 4 and (left in right or right in left):
            return True
        if abs(len(left) - len(right)) > 2 or min(len(left), len(right)) < 4:
            return False
        return SequenceMatcher(None, left, right).ratio() >= 0.78

    def _query_hit(self, event, query):
        if not query:
            return True
        if self._name_mentions_artist(event.get("headliner"), query):
            return True
        if self._name_mentions_artist(event.get("event_name"), query):
            return True
        if self._name_mentions_artist(event.get("venue"), query):
            return True
        if self._name_mentions_artist(event.get("organizer"), query):
            return True
        stop = {"at", "the", "and", "with", "for", "in", "on", "to", "a", "an"}
        tokens = [
            token for token in re.split(r"\W+", (query or "").lower())
            if token
            and token not in stop
            and (len(token) >= 2 or (len(token) == 1 and token.isalpha()))
        ]
        if len(tokens) < 2:
            return False
        haystack = " ".join(
            str(part or "")
            for part in (
                event.get("headliner"),
                event.get("event_name"),
                event.get("venue"),
                event.get("city"),
                event.get("organizer"),
            )
        ).lower()
        return all(re.search(rf"\b{re.escape(token)}\b", haystack) for token in tokens)

    def _min_ticket_price(self, ticket_info):
        text = (ticket_info or "").strip()
        if not text:
            return None
        lowered = text.lower()
        amounts = [float(match) for match in re.findall(r"\$\s*(\d+(?:\.\d+)?)", text)]
        if re.search(r"\bfree\b", lowered):
            if not amounts:
                return 0.0
            return 0.0
        if amounts:
            return min(amounts)
        return None

    def _price_rank(self, event, max_price):
        price = self._min_ticket_price(event.get("ticket_info"))
        if max_price is None:
            return (1, price if price is not None else 10**6)
        if price is None:
            return (1, 10**6)
        if price <= max_price:
            return (0, price)
        return None

    def _event_place_row(self, event):
        return match_place(self._venue_index(), event.get("venue") or "", event.get("city") or "")

    def _annotate_events_near_transit(self, events, city="", origin_station=None):
        """
        Optional enrichment when we happen to have curated stations for a city.
        Never filters/drops events — deep mode researches transit per city instead.
        If origin_station=(name, lat, lng) is set, also score rail-trip proxy from that stop.
        """
        try:
            from services.neighborhoods import (
                nearest_transit_station,
                transit_stations_for_city,
                haversine_miles,
                TRANSIT_EXPAND_MILES,
            )
        except ImportError:
            from neighborhoods import (
                nearest_transit_station,
                transit_stations_for_city,
                haversine_miles,
                TRANSIT_EXPAND_MILES,
            )
        stations = transit_stations_for_city(city)
        if not stations:
            return list(events), {"annotated": 0, "reason": "no_local_station_data"}

        origin_name = None
        origin_lat = origin_lng = None
        if origin_station and len(origin_station) >= 3:
            origin_name, origin_lat, origin_lng = (
                origin_station[0], origin_station[1], origin_station[2]
            )

        out = []
        annotated = 0
        for event in events or []:
            packed = dict(event)
            place = self._event_place_row(event)
            lat = (place or {}).get("lat")
            lng = (place or {}).get("lng")
            if lat is not None and lng is not None:
                hit = nearest_transit_station(lat, lng, city=city, stations=stations)
                if hit and hit[0] <= TRANSIT_EXPAND_MILES:
                    miles, station = hit
                    packed["_transit_miles"] = round(miles, 2)
                    packed["_transit_station"] = station
                    annotated += 1
                    if origin_name:
                        packed["_transit_origin"] = origin_name
                        # Proxy: distance between origin stop and venue stop.
                        dest = None
                        for item in stations:
                            if len(item) >= 3 and item[0] == station:
                                dest = item
                                break
                        if dest and origin_lat is not None:
                            hop = haversine_miles(origin_lat, origin_lng, dest[1], dest[2])
                            if hop is not None:
                                packed["_transit_from_origin_miles"] = round(hop, 2)
            out.append(packed)
        return out, {
            "annotated": annotated,
            "reason": "optional_enrichment",
            "origin_station": origin_name,
        }

    def _filter_events_near_transit(self, events, city="", radius_miles=None, expand_miles=None):
        """Deprecated filter path — annotate only; never empty the catalog for transit."""
        return self._annotate_events_near_transit(events, city=city)

    def _resolve_origin_station(self, city, origin_text="", latest=""):
        """Map 'Judkins station' / origin hint to a known stop when we have local data."""
        try:
            from services.neighborhoods import match_station_by_name, transit_stations_for_city
        except ImportError:
            from neighborhoods import match_station_by_name, transit_stations_for_city
        stations = transit_stations_for_city(city)
        if not stations:
            return None
        blob = f"{origin_text or ''} {latest or ''}".strip()
        if not blob:
            return None
        # Prefer explicit "... station" phrases.
        candidates = []
        for match in re.finditer(
            r"\b(?:near|by|at|from|close to|live(?:s)? near|off)\s+(?:the\s+)?([a-z0-9][\w'’.\- ]{1,40}?)\s+stations?\b",
            blob,
            re.I,
        ):
            candidates.append(match.group(1))
        for match in re.finditer(
            r"\b([a-z0-9][\w'’.\-]{2,40}?)\s+stations?\b",
            blob,
            re.I,
        ):
            candidates.append(match.group(1))
        if origin_text:
            candidates.append(origin_text)
        for cand in candidates:
            hit = match_station_by_name(cand, city=city, stations=stations)
            if hit:
                return hit
        return None

    def _text_mentions_genre(self, text, genre=""):
        raw = (text or "").strip()
        if not raw:
            return False
        lowered = raw.lower()
        if genre:
            for stem in self._genre_stems(genre):
                if len(stem) >= 3 and re.search(rf"\b{re.escape(stem)}\b", lowered):
                    return True
        for family, members in GENRE_FAMILIES.items():
            for name in (family, *members):
                if len(name) < 3:
                    continue
                if re.search(rf"\b{re.escape(name)}\b", lowered):
                    return True
        return False

    def _venue_index(self):
        now = datetime.now(timezone.utc)
        if self._place_index is not None and self._place_index_at and now - self._place_index_at < PLACE_CACHE_TTL:
            return self._place_index
        rows = []
        if self.list_venue_places:
            try:
                rows = self.list_venue_places() or []
            except Exception as exc:
                logger.warning("venue place cache load failed: %s", exc)
        self._place_index = load_place_index(rows)
        self._place_index_at = now
        return self._place_index

    def _all_events(self):
        now = datetime.now(timezone.utc)
        if self._events_cache is not None and self._events_cache_at and now - self._events_cache_at < PLACE_CACHE_TTL:
            return self._events_cache
        rows = []
        try:
            rows = self.list_events() or []
        except Exception as exc:
            logger.warning("event catalog load failed: %s", exc)
        self._events_cache = rows
        self._events_cache_at = now
        return self._events_cache

    def _name_mentions_artist(self, event_name, query):
        name = event_name or ""
        needle = re.sub(r"\s+", " ", (query or "").strip())
        if len(needle) < 2 or not name:
            return False
        if re.search(rf"\b{re.escape(needle)}\b", name, re.I):
            return True
        compact_name = re.sub(r"[^a-z0-9]+", "", name.lower())
        compact_needle = re.sub(r"[^a-z0-9]+", "", needle.lower())
        if len(compact_needle) >= 5 and compact_needle in compact_name:
            return True
        words = [word for word in re.split(r"\W+", name.lower()) if len(word) >= 4]
        return any(
            abs(len(compact_needle) - len(word)) <= 2
            and SequenceMatcher(None, compact_needle, word).ratio() >= 0.86
            for word in words
        )

    def _artist_events(self, query, limit=8):
        needle = re.sub(r"\s+", " ", (query or "").strip().lower())
        if len(needle) < 2:
            return []
        today = self._clock()["today"]
        hits = []
        for event in self._drop_past_events(self._all_events(), today):
            packed = compact_event(event) or {}
            # Prefer full row fields: compact_event may omit headliner.
            if (
                self._name_mentions_artist(event.get("headliner"), needle)
                or self._name_mentions_artist(event.get("event_name"), needle)
                or self._name_mentions_artist(packed.get("event_name"), needle)
            ):
                hits.append(packed if packed else event)
        hits.sort(key=lambda event: (
            0 if (event.get("event_name") or "").strip().lower() == needle else 1,
            self._event_date(event) or date.max,
        ))
        return hits[:limit]

    def _catalog_artist_card(self, query):
        query = (query or "").strip()
        if not query:
            return None
        events = self._artist_events(query)
        if not events:
            return None
        genres = []
        seen = set()
        for event in events:
            for part in re.split(r"[,/;|]+", event.get("genre") or ""):
                tag = self._norm_genre(part)
                if tag and tag not in seen:
                    seen.add(tag)
                    genres.append(tag)
        next_show = events[0]
        when = self._human_day(self._event_date(next_show)) or (next_show.get("date") or "").strip()
        venue = self._sms_venue(next_show.get("venue") or "")
        city = (next_show.get("city") or "").strip()
        place = ", ".join(part for part in (venue, city) if part)
        title = next_show.get("event_name") or query
        lines = []
        if genres:
            lines.append(f"{query} is tagged {', '.join(genres[:4])} on the flyers.")
        else:
            lines.append(f"{query} is on the calendar.")
        if when:
            lines.append(f"{when}: {title}")
        elif title:
            lines.append(title)
        if place:
            lines.append(place)
        return {
            "name": query,
            "genres": genres,
            "shows": events[:3],
            "sms": "\n".join(lines),
            "source": "catalog",
        }

    def _heat_index(self):
        now = datetime.now(timezone.utc)
        if self._heat_cache is not None and self._heat_cache_at and now - self._heat_cache_at < PLACE_CACHE_TTL:
            return self._heat_cache
        rows = []
        if self.list_artist_heat:
            try:
                rows = self.list_artist_heat() or []
            except Exception as exc:
                logger.warning("artist heat cache load failed: %s", exc)
        self._heat_cache = load_heat_index(rows) or {}
        self._heat_cache_at = now
        self._artist_heat = {
            key: heat_popularity(row)
            for key, row in self._heat_cache.items()
        }
        return self._heat_cache

    def _artist_row(self, name):
        return match_heat(self._heat_index(), name)

    def _artist_pop(self, name):
        return heat_popularity(self._artist_row(name))

    def _show_clone(self, left, right):
        if left.get("id") and left.get("id") == right.get("id"):
            return True
        left_key = venue_key(left.get("venue") or "", left.get("city") or "")
        right_key = venue_key(right.get("venue") or "", right.get("city") or "")
        if left_key and left_key == right_key and self._event_date(left) == self._event_date(right):
            return True
        left_art = (self._show_artists([left]) or [""])[0].lower()
        right_art = (self._show_artists([right]) or [""])[0].lower()
        return bool(left_art and right_art and left_art == right_art)

    def _timing_score(self, day, wanted_day):
        today = datetime.now(US_TZ).date()
        if not day or getattr(day, "year", 0) >= 9999:
            return 0.15
        days = (day - today).days
        if days < 0:
            return 0.0
        if wanted_day:
            return 1.0
        return 1.0 / (1.0 + (days / 28.0))

    def _use_timing(self, wanted_day=None):
        return bool(wanted_day) or self._message_names_a_day(self._latest_user_text)

    def _show_health(self, item, wanted_day=None, preferred=False, use_timing=False):
        score, parts = score_show(
            item.get("artist_pop"),
            item.get("breakout"),
            item.get("venue_score"),
        )
        timing = self._timing_score(item.get("day"), wanted_day) if use_timing else 0.0
        if use_timing:
            score += 0.12 * timing
        if preferred:
            score += 0.05
        parts = {**parts, "timing": round(timing, 3)}
        return score, parts

    def _diversify_shows(self, events, limit, wanted_day=None, prefer_genres=None):
        try:
            limit = min(max(int(limit or 3), 1), 8)
        except (TypeError, ValueError):
            limit = 3
        if not events:
            return []
        if len(events) == 1:
            artists = self._show_artists(events[:1])
            return [{"event": events[0], "artist": artists[0] if artists else "", "why": "health", "health": 0}]
        index = self._venue_index()
        try:
            heat = self._heat_index() or {}
        except Exception as exc:
            logger.warning("artist heat index failed: %s", exc)
            heat = {}
        annotated = []
        for event in events:
            place = match_place(index, event.get("venue") or "", event.get("city") or "")
            artists = self._show_artists([event])
            artist = artists[0] if artists else ""
            row = match_heat(heat, artist)
            item = {
                "event": event,
                "venue_score": venue_score(place) if place and place.get("place_id") else None,
                "artist": artist,
                "day": self._event_date(event) or date(9999, 12, 31),
                "artist_pop": heat_popularity(row) if row else 0,
                "breakout": heat_breakout(row) if row else None,
            }
            preferred = bool(prefer_genres) and self._genre_hit(event, prefer_genres)
            use_timing = self._use_timing(wanted_day)
            health, parts = self._show_health(
                item,
                wanted_day=wanted_day,
                preferred=preferred,
                use_timing=use_timing,
            )
            item["health"] = health
            item["health_parts"] = parts
            item["why"] = "health"
            annotated.append(item)

        if self._use_timing(wanted_day):
            remaining = sorted(annotated, key=lambda item: (-item["health"], item["day"]))
        else:
            remaining = sorted(annotated, key=lambda item: (-item["health"], str(item["event"].get("id") or "")))
        picked = []

        def is_clone(item):
            event = item["event"]
            return any(self._show_clone(event, other["event"]) for other in picked)

        for item in remaining:
            if len(picked) >= limit:
                break
            if is_clone(item):
                continue
            picked.append(item)
        return picked[:limit]

    def _search_picks(self, rows):
        picks = []
        for row in rows or []:
            event = row.get("event") or {}
            artist = row.get("artist") or ""
            if not artist:
                names = self._show_artists([event])
                artist = names[0] if names else ""
            picks.append({
                "why": "health",
                "health": round(float(row.get("health") or 0), 3),
                "parts": row.get("health_parts") or {},
                "artist": artist,
                "event_name": event.get("event_name"),
                "venue": self._sms_venue(event.get("venue") or ""),
            })
        return picks

    def _mix_talk(self, city, genre, wanted_day, picks):
        if genre and city:
            ask = f"{genre} in {city}"
        elif city:
            ask = f"{city} shows"
        elif genre:
            ask = genre
        else:
            ask = ""
        if wanted_day:
            when = self._human_window(*wanted_day) if isinstance(wanted_day, tuple) else self._human_day(wanted_day)
            ask = f"{ask} {when}".strip() if ask else (when or "")
        n = len([pick for pick in (picks or []) if pick])
        if n <= 1:
            count = "this one scores highest overall"
        elif n == 2:
            count = "these two score highest overall"
        else:
            count = "these three score highest overall"
        if ask:
            return f"Best {ask} I have — {count}."
        return count[0].upper() + count[1:] + "."

    def _profile_data(self, phone_number):
        result = self.get_user(phone_number) or {}
        data = dict(result.get("data") or {})
        data["city_list"] = self._clean_list(data.get("city_list"))
        data["genre_list"] = self._clean_list(data.get("genre_list"))
        return data

    def _search_for_texter(self, phone_number, arguments):
        profile = self._profile_data(phone_number)
        saved_genres = profile.get("genre_list") or []
        explicit_genre = self._clean_label(arguments.get("genre") or "")
        query = arguments.get("q")
        # Only apply a city when the tool/user named one — never fall back to saved city_list.
        city = (arguments.get("city") or "").strip()
        neighborhood = (arguments.get("neighborhood") or "").strip() or None
        if query:
            query = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", query)
            query = re.sub(r"\b\d+\s*(bucks?|dollars?)\b", " ", query, flags=re.I)
            # Transit is handled by station-distance filtering — never as a text query.
            query = re.sub(
                r"\b(light\s*rails?|link(\s*light\s*rail)?|public\s+transport(ation)?|"
                r"transit|metro|bus|uber|lyft|walkable|parking)\b",
                " ",
                query,
                flags=re.I,
            )
            query = re.sub(r"\s+", " ", query).strip() or None
        if query:
            query, city = self._peel_city_from_query(query, city)
        date = arguments.get("date")
        latest = self._latest_user_text or ""
        constraints = self._constraint_flags(latest)
        wants_transit = bool(constraints.get("transit"))
        # Also treat explicit tool hints / residual q as transit intent.
        if not wants_transit and re.search(
            r"\b(light\s*rail|public\s+transport|transit|"
            r"(?:no|without)\s+(?:a\s+)?car|"
            r"(?:won'?t|wont|don'?t|dont)\s+have\s+(?:a\s+)?car|car[- ]?free)\b",
            f"{latest} {arguments.get('q') or ''} {neighborhood or ''}",
            re.I,
        ):
            wants_transit = True
        # Station phrases imply transit intent ("near Judkins station").
        if not wants_transit and re.search(r"\b\w[\w'’.\- ]{1,30}\s+stations?\b", latest, re.I):
            wants_transit = True
        deep_hints = ((getattr(self, "_deep_constraints", None) or {}).get("hints") or {})
        if (deep_hints.get("transit") or "").lower() in {
            "link_rail", "light_rail", "rail", "link", "bus", "transit", "max", "trimet",
        }:
            wants_transit = True
        if not city and deep_hints.get("city"):
            city = str(deep_hints.get("city")).strip()
        # Taste stickiness: only hard-filter genre if THIS message named one —
        # unless session slots are driving the search (follow-up refine).
        if explicit_genre and not self._text_mentions_genre(latest, explicit_genre):
            if not getattr(self, "_slots_driven", False):
                explicit_genre = ""
        if not explicit_genre and deep_hints.get("genre"):
            hint_genre = self._clean_label(deep_hints.get("genre"))
            if hint_genre and self._text_mentions_genre(latest, hint_genre):
                explicit_genre = hint_genre
        judgment = getattr(self, "_last_judgment", None) or {}
        if not explicit_genre and judgment.get("genre"):
            judge_genre = self._clean_label(judgment.get("genre"))
            if judge_genre and self._text_mentions_genre(latest, judge_genre):
                explicit_genre = judge_genre
        if not neighborhood and deep_hints.get("neighborhood"):
            neighborhood = str(deep_hints.get("neighborhood")).strip() or None
        origin = (deep_hints.get("origin") or "").strip() or None
        if query:
            query, peeled_hood = self._peel_neighborhood(query, city)
            if peeled_hood and not neighborhood:
                neighborhood = peeled_hood
        if latest:
            _, peeled_hood = self._peel_neighborhood(latest, city)
            if peeled_hood and not neighborhood and not origin:
                # "staying in X" → origin, not venue filter.
                if re.search(
                    r"\b(staying\s+in|i'?m\s+in|im\s+in|i\s+am\s+in|based\s+in|coming\s+from)\b",
                    latest,
                    re.I,
                ):
                    origin = peeled_hood
                else:
                    neighborhood = peeled_hood
        # No-car / transit + a stay/base area: search rail-accessible citywide from that origin.
        if wants_transit and origin and neighborhood and origin.lower() == neighborhood.lower():
            neighborhood = None
        if wants_transit and origin and not neighborhood:
            neighborhood = None
        # Transit asks must use station distance — never a Downtown neighborhood proxy.
        if wants_transit:
            hood_l = (neighborhood or "").strip().lower()
            if hood_l in {
                "downtown", "city center", "centre", "center", "light rail",
                "link", "transit", "the light rail", "station", "the station",
                "bellevue", "redmond", "kirkland", "tacoma", "everett", "renton",
                "southwest", "southeast", "northeast", "northwest", "sw", "se", "ne", "nw",
            }:
                if not origin:
                    origin = neighborhood
                neighborhood = None
        # Resolve "Judkins station" etc. to a known stop for origin-aware ranking/labels.
        origin_station = self._resolve_origin_station(city, origin_text=origin or "", latest=latest)
        if origin_station and not origin:
            origin = origin_station[0]
        force_history_date = bool(getattr(self, "_force_date_from_history", False))
        if date and not self._message_names_a_day(latest) and not force_history_date:
            date = None
        wanted_start, wanted_end = self._parse_date_window(latest)
        if wanted_start is None:
            wanted_start, wanted_end = self._parse_date_window(date)
        if wanted_start is None and (self._is_show_followup(latest) or force_history_date):
            if hasattr(self, "_date_from_recent_history"):
                wanted_start, wanted_end = self._date_from_recent_history()
        # Judgment / deep-resolver date_phrase can recover "next weekend" if model omitted date.
        if wanted_start is None:
            judgment = getattr(self, "_last_judgment", None) or {}
            wanted_start, wanted_end = self._parse_date_window(judgment.get("date_phrase") or "")
        if wanted_start is None:
            deep_hints = ((getattr(self, "_deep_constraints", None) or {}).get("hints") or {})
            wanted_start, wanted_end = self._parse_date_window(deep_hints.get("date_phrase") or "")
        wanted_day = wanted_start if wanted_start and wanted_start == wanted_end else None
        wanted_window = (wanted_start, wanted_end) if wanted_start else None
        max_price = arguments.get("max_price")
        try:
            max_price = float(max_price) if max_price is not None and max_price != "" else None
        except (TypeError, ValueError):
            max_price = None
        try:
            limit = min(max(int(arguments.get("limit") or 5), 1), 8)
        except (TypeError, ValueError):
            limit = 5

        today = self._clock()["today"]
        events = self._drop_past_events(self._all_events(), today, date)
        city_l = (city or "").strip().lower()
        upcoming = []
        for event in events:
            packed = compact_event(event)
            if not packed:
                continue
            if city_l and not self._city_hit(packed, city_l):
                continue
            upcoming.append(packed)

        transit_meta = None
        if wants_transit and upcoming:
            # Optional stop labels when we have local station data — never filter/drop.
            hood_city = city or (upcoming[0].get("city") or "")
            upcoming, transit_meta = self._annotate_events_near_transit(
                upcoming,
                hood_city,
                origin_station=origin_station,
            )
            logger.info(
                "transit annotate city=%s annotated=%s origin=%s reason=%s",
                hood_city,
                (transit_meta or {}).get("annotated"),
                (transit_meta or {}).get("origin_station"),
                (transit_meta or {}).get("reason"),
            )
        logger.info(
            "search_events city=%s genre=%s date=%s..%s neighborhood=%s q=%s transit=%s upcoming=%s",
            city,
            explicit_genre or None,
            wanted_start,
            wanted_end,
            neighborhood,
            query,
            wants_transit,
            len(upcoming),
        )

        neighborhood_venues = None
        if neighborhood and upcoming:
            hood_city = city or (upcoming[0].get("city") or "")
            if hood_city:
                venue_pool = self._unique_event_venues(upcoming)
                neighborhood_venues = self._match_neighborhood_venues(
                    hood_city, neighborhood, venue_pool
                )
                if neighborhood_venues:
                    hood_hits = [
                        event for event in upcoming
                        if self._event_in_venues(event, neighborhood_venues)
                    ]
                    # Transit + real neighborhood: prefer intersection; if empty keep transit set.
                    if hood_hits or not wants_transit:
                        upcoming = hood_hits
                    elif wants_transit:
                        logger.info(
                            "neighborhood %s empty after transit; keeping transit matches",
                            neighborhood,
                        )
                elif not wants_transit:
                    # Structured miss: do not silently widen to the whole city.
                    upcoming = []

        dated = [
            event for event in upcoming
            if self._in_date_window(self._event_date(event), wanted_start, wanted_end)
        ] if wanted_start else list(upcoming)

        def rank_events(pool, use_query, soonest_first, use_genre=True):
            ranked = []
            for event in pool:
                if use_query and not self._query_hit(event, query):
                    continue
                if use_genre and explicit_genre and not self._genre_hit(event, [explicit_genre]):
                    continue
                price_rank = self._price_rank(event, max_price)
                if price_rank is None:
                    continue
                preferred = 0 if (
                    not explicit_genre
                    and saved_genres
                    and self._genre_hit(event, saved_genres)
                ) else 1
                day = self._event_date(event) or date(9999, 12, 31)
                tie = str(event.get("id") or event.get("event_name") or "")
                walk_rank = float(event.get("_transit_miles") or 99)
                from_origin = event.get("_transit_from_origin_miles")
                # Prefer short rail hop from origin stop, then short walk from destination stop.
                transit_rank = (
                    float(from_origin) if from_origin is not None else walk_rank + 50
                )
                if wants_transit:
                    ranked.append((transit_rank, walk_rank, preferred, day, price_rank[0], price_rank[1], tie, event))
                elif soonest_first:
                    ranked.append((preferred, day, price_rank[0], price_rank[1], tie, event))
                else:
                    ranked.append((preferred, price_rank[0], price_rank[1], day, tie, event))
            ranked.sort()
            return ranked

        soonest = (
            self._message_names_a_day(latest)
            or bool(query)
            or bool(wanted_start)
            or bool(neighborhood)
            or wants_transit
        )
        ranked = rank_events(dated, bool(query), soonest, True)
        used_query = query
        query_missed = False
        genre_relaxed = False
        if query and not ranked:
            query_missed = True
        elif explicit_genre and not ranked:
            ranked = rank_events(dated, False, soonest, False)
            genre_relaxed = bool(ranked)
        elif not ranked and dated and not query:
            ranked = [(1, date(9999, 12, 31), 1, 10**6, str(event.get("id") or ""), event) for event in dated]
            genre_relaxed = bool(explicit_genre)
        pool = [item[-1] for item in ranked]
        prefer = saved_genres if not explicit_genre else None
        take = min(limit, 2)

        def unranked_rows(events):
            return [
                {"event": event, "artist": "", "why": "unranked", "health": 0}
                for event in events[:take]
            ]

        try:
            picked = self._diversify_shows(
                pool,
                take,
                wanted_day=wanted_start,
                prefer_genres=prefer,
            )
            if not picked and pool:
                picked = unranked_rows(pool)
        except Exception as exc:
            logger.exception("show ranking failed; returning unranked matches")
            picked = unranked_rows(pool)
        data = [row["event"] for row in picked]
        picks = self._search_picks(picked)
        seen = {event.get("id") for event in data}

        later_ranked = rank_events(upcoming, bool(used_query), True, not genre_relaxed)
        if used_query and not later_ranked and not query_missed:
            later_ranked = rank_events(upcoming, False, True)
        later = []
        close_day = wanted_end or wanted_start
        for item in later_ranked:
            event = item[-1]
            event_id = event.get("id")
            event_day = self._event_date(event)
            if event_id in seen:
                continue
            if close_day and event_day is not None and event_day <= close_day:
                continue
            later.append(event)
            if len(later) >= min(limit, 3):
                break
        if not wanted_start and data:
            later = []
        if query_missed:
            later = []

        place_label = (
            f"{neighborhood}, {city}" if neighborhood and city
            else (neighborhood or city)
        )
        origin_label = (origin_station[0] if origin_station else None) or origin
        if wants_transit and city:
            rail = "MAX" if "portland" in (city or "").lower() else "light-rail"
            if origin_label:
                place_label = f"{rail}-accessible {city} from {origin_label}"
            else:
                place_label = f"{rail}-accessible {city}"
        elif wants_transit:
            place_label = "near transit"
        elif origin_label and city:
            place_label = f"{city} (from {origin_label})"
        summary = self._search_summary(
            city=place_label,
            genre=explicit_genre,
            wanted_day=wanted_start,
            data=data,
            later=later,
            genre_relaxed=genre_relaxed,
            wanted_label=self._human_window(wanted_start, wanted_end),
            query=query if query_missed else None,
        )
        sms_shows = [self._format_sms_show(event) for event in data[:2]]
        sms_later = [self._format_sms_show(event) for event in later[:1]]
        artists = self._show_artists(data[:2] or later[:1])
        opener = self._mix_talk(place_label, explicit_genre, wanted_window or wanted_day, picks)
        if getattr(self, "_deep_mode", False):
            # Deep mode: model writes the why; avoid the generic ranked opener.
            opener = ""
        applied_date = None
        if wanted_start and wanted_end:
            applied_date = (
                wanted_start.isoformat()
                if wanted_start == wanted_end
                else f"{wanted_start.isoformat()}/{wanted_end.isoformat()}"
            )
        self._last_sms_pack = {
            "shows": sms_shows,
            "later": sms_later,
            "artists": artists,
            "place": place_label or "that city",
            "wanted_day": applied_date,
            "opener": opener,
            "picks": picks,
            "deep": bool(getattr(self, "_deep_mode", False)),
            "transit": bool(wants_transit),
            "origin": origin_label,
            "origin_station": origin_station[0] if origin_station else None,
        }
        return {
            "total": len(ranked),
            "limit": limit,
            "offset": 0,
            "data": data,
            "later": later,
            "picks": picks,
            "sms": {"shows": sms_shows, "later": sms_later, "opener": opener},
            "summary": summary,
            "applied": {
                "city": city,
                "neighborhood": neighborhood,
                "origin": origin_label,
                "origin_station": origin_station[0] if origin_station else None,
                "neighborhood_venues": len(neighborhood_venues or []) if neighborhood else None,
                "transit": wants_transit,
                "transit_annotated": (transit_meta or {}).get("annotated"),
                "date": applied_date,
                "genre": explicit_genre or None,
                "genre_relaxed": genre_relaxed,
                "saved_genre_soft": bool(prefer),
                "query": query,
            },
        }

    def _search_summary(self, city, genre, wanted_day, data, later, genre_relaxed=False, wanted_label=None, query=None):
        place = city or "that city"
        label = genre or "matching"
        when = wanted_label or (wanted_day.isoformat() if wanted_day else None)
        if query:
            return f"No shows matching {query} in {place}."
        if wanted_day and not data and later:
            nxt = later[0]
            nxt_day = self._event_date(nxt)
            nxt_when = f"{nxt_day.strftime('%b')} {nxt_day.day}" if nxt_day else "later"
            return (
                f"No {label} shows in {place} on {when}. "
                f"Next: {nxt.get('event_name')} on {nxt_when}."
            )
        if wanted_day and data and later:
            return f"{len(data)} {label} show(s) in {place} on {when}, plus {len(later)} later."
        if not data and later:
            nxt = later[0]
            nxt_day = self._event_date(nxt)
            when = f"{nxt_day.strftime('%b')} {nxt_day.day}" if nxt_day else "later"
            return f"No {label} shows now in {place}. Next: {nxt.get('event_name')} on {when}."
        if not data:
            return f"No {label} shows found in {place}."
        if genre_relaxed:
            return f"Could not lock {label} cleanly. Closest {len(data)} show(s) in {place}."
        return f"{len(data)} {label} show(s) in {place}."

    def _show_artists(self, events):
        seen = set()
        artists = []
        for event in events or []:
            for artist in headliners_for_event(event, limit=3):
                key = artist.lower()
                if key in seen:
                    continue
                seen.add(key)
                artists.append(artist)
                if len(artists) >= 3:
                    return artists
        return artists

    def _completion_model(self):
        """Fast path uses OPENAI_MODEL; deep investigation uses OPENAI_DEEP_MODEL."""
        if getattr(self, "_deep_mode", False):
            return self.deep_model or self.model
        return self.model

    def _chat_completion(self, *, model, messages, temperature=None, max_tokens=None, **kwargs):
        """Chat Completions wrapper — gpt-5+ wants max_completion_tokens."""
        payload = {"model": model, "messages": messages, **kwargs}
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            if str(model).startswith(("gpt-5", "o1", "o3", "o4")):
                payload["max_completion_tokens"] = max_tokens
            else:
                payload["max_tokens"] = max_tokens
        try:
            return self._client.chat.completions.create(**payload)
        except Exception as exc:
            err = str(exc).lower()
            if "temperature" in err and "temperature" in payload:
                payload.pop("temperature", None)
                return self._client.chat.completions.create(**payload)
            if "max_tokens" in err and "max_tokens" in payload:
                payload["max_completion_tokens"] = payload.pop("max_tokens")
                return self._client.chat.completions.create(**payload)
            if "max_completion_tokens" in err and "max_completion_tokens" in payload:
                payload["max_tokens"] = payload.pop("max_completion_tokens")
                return self._client.chat.completions.create(**payload)
            raise

    def warm_caches(self, force=False):
        """Compatibility no-op — flask_app may call this on SMS warm."""
        return {"ok": True, "forced": bool(force)}

    def _ensure_user(self, phone_number):
        result = self.get_user(phone_number) or {}
        if result.get("success") and result.get("data"):
            return result["data"]
        created = self.create_user(phone_number) or {}
        return created.get("data")

    def _complete(self, phone_number, messages, max_rounds=None):
        rounds = MAX_TOOL_ROUNDS if max_rounds is None else max_rounds
        model = self._completion_model()
        deep = bool(getattr(self, "_deep_mode", False))
        logger.info(
            "sms complete model=%s deep=%s rounds=%s for %s",
            model,
            deep,
            rounds,
            phone_number[-4:] if phone_number else "",
        )
        for _ in range(rounds + 1):
            kwargs = {
                "model": model,
                "messages": messages,
                "tools": TOOLS,
                "tool_choice": "auto",
            }
            # Reasoning-oriented deep models are often happier without a high temperature.
            if deep:
                kwargs["temperature"] = 0.2
            else:
                kwargs["temperature"] = 0.4
            try:
                response = self._chat_completion(**kwargs)
            except Exception as exc:
                # Some models reject temperature — retry once without it.
                if "temperature" in str(exc).lower() and "temperature" in kwargs:
                    kwargs.pop("temperature", None)
                    response = self._chat_completion(**kwargs)
                else:
                    raise
            choice = response.choices[0].message
            if not choice.tool_calls:
                text = (choice.content or "").strip() or "I didn't catch that. Try a city or genre?"
                if self._last_sms_pack and (self._last_sms_pack.get("shows") or self._last_sms_pack.get("later")):
                    return self._compose_sms_reply(text, self._last_sms_pack)
                if self._spotify_card_sms:
                    return self._spotify_card_sms
                return text

            messages.append({
                "role": "assistant",
                "content": choice.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in choice.tool_calls
                ],
            })
            for call in choice.tool_calls:
                arguments = {}
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                tool_result = self._call_tool(phone_number, call.function.name, arguments)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": tool_result,
                })
        return "That search got too long. Try a more specific city or genre?"

    def _bare_city_search(self, phone_number, arguments):
        city = (arguments.get("city") or "").strip()
        today = self._clock()["today"]
        hits = []
        city_l = city.lower()
        for event in self._drop_past_events(self._all_events(), today):
            packed = compact_event(event)
            if not packed:
                continue
            if city_l and not self._city_hit(packed, city_l):
                continue
            hits.append(packed)
            if len(hits) >= 3:
                break
        sms = [self._format_sms_show(event) for event in hits]
        self._last_sms_pack = {
            "shows": sms,
            "later": [],
            "artists": self._show_artists(hits),
            "place": city or "that city",
            "wanted_day": None,
            "opener": "",
        }
        return {
            "error": "search_failed",
            "data": hits,
            "later": [],
            "sms": {"shows": sms, "later": [], "opener": ""},
            "summary": f"Ranking hit a snag. Closest {city or 'matching'} shows I still have.",
        }

    def _call_tool(self, phone_number, name, arguments):
        try:
            if name == "search_events":
                result = self._search_for_texter(phone_number, arguments)
                return json.dumps(result, default=str)

            if name == "get_event":
                event = compact_event(self.get_event(int(arguments.get("event_id"))))
                packed = {"error": "not found"}
                if event:
                    sms = self._format_sms_show(event)
                    packed = event
                    packed["sms"] = sms
                    self._last_sms_pack = {
                        "shows": [sms],
                        "later": [],
                        "artists": self._show_artists([event]),
                        "place": event.get("city") or "that city",
                        "wanted_day": None,
                    }
                return json.dumps(packed)

            if name == "add_event":
                return json.dumps({"error": "Adding events over SMS is off. Use the site."})

            if name == "lookup_venue":
                card = self._lookup_venue_card(
                    arguments.get("venue") or arguments.get("q") or "",
                    arguments.get("city") or "",
                )
                return json.dumps(card)

            if name == "rank_venues":
                card = self._rank_venues_card(
                    arguments.get("city") or arguments.get("q") or "",
                    arguments.get("limit") or 3,
                )
                return json.dumps(card)

            if name == "lookup_artist":
                query = arguments.get("artist") or arguments.get("q") or ""
                catalog = self._catalog_artist_card(query)
                latest = (self._latest_user_text or "").lower()
                wants_listen = bool(re.search(r"\b(spotify|listen|song|track)\b", latest))
                card = {}
                if wants_listen or not catalog:
                    if getattr(self.spotify, "enabled", False):
                        card = self.spotify.lookup_artist(query) or {}
                if catalog:
                    card = dict(card or {})
                    card["catalog_genres"] = catalog.get("genres") or []
                    card["catalog_sms"] = catalog.get("sms")
                    if not card.get("genres"):
                        card["genres"] = catalog.get("genres") or []
                    if not wants_listen or not card.get("sms"):
                        card["sms"] = catalog.get("sms")
                sms = (card or {}).get("sms")
                if sms and wants_listen:
                    self._spotify_card_sms = sms
                return json.dumps(card or {"error": "missing_artist"}, default=str)

            if name == "research_local" or name == "research_transit":
                city = arguments.get("city") or ""
                topic = arguments.get("topic") or ""
                origin = arguments.get("origin") or ""
                if name == "research_transit" and not topic:
                    topic = "public transit"
                card = research_local(city, topic=topic, origin=origin)
                return json.dumps(card or {"found": False}, default=str)

            if name == "lookup_context":
                card = lookup_context(arguments.get("q") or arguments.get("query") or arguments.get("artist") or "")
                return json.dumps(card or {"found": False}, default=str)

            if name == "list_favorites":
                result = self.get_favorites(phone_number) or {}
                favorites = [
                    compact_event(event)
                    for event in (result.get("data") or [])[:20]
                ]
                favorites = [event for event in favorites if event]
                sms = [self._format_sms_show(event) for event in favorites[:3]]
                self._last_sms_pack = {
                    "shows": sms,
                    "later": [],
                    "artists": self._show_artists(favorites[:3]),
                    "place": "your favorites",
                    "wanted_day": None,
                }
                return json.dumps({"favorites": favorites, "sms": {"shows": sms}})

            return json.dumps({"error": f"unknown tool {name}"})
        except Exception as exc:
            logger.exception("SMS tool %s failed", name)
            if name == "search_events":
                try:
                    return json.dumps(self._bare_city_search(phone_number, arguments or {}), default=str)
                except Exception:
                    logger.exception("SMS bare search failed")
                    return json.dumps({
                        "error": "search_failed",
                        "data": [],
                        "later": [],
                        "summary": "Search hit a snag. Try the city and genre again.",
                    })
            return json.dumps({"error": str(exc)})
