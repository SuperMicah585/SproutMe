import json
import logging
import re
from datetime import datetime, timezone, timedelta, date
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

from services.public_api import compact_event, clean_event_url
from services.artist_heat import heat_breakout, heat_popularity, load_heat_index, match_heat
from services.show_health import display_score, score_show
from services.spotify_service import SpotifyCatalog, headliners_for_event
from services.venue_places import load_place_index, match_place, place_cache_row, rank_places, venue_key, venue_score
from services.web_lookup import lookup_context

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
# Show SproutMe score (artist / heat / room), not Google venue reviews.
SHOW_RATING_RE = re.compile(
    r"(?:"
    r"\b(sprout(?:me)?\s+score|show\s+score|show\s+rating)\b|"
    r"\b(rating|score)\b.{0,40}\b(show|gig|event|night|one)\b|"
    r"\b(this|that|the)\s+(show|gig|event|one)\b.{0,40}\b(rating|score)\b|"
    r"\b(why|how).{0,24}\b(this |that |the )?(score|rated|ranking|rate)\b|"
    r"\b(break\s*down|explain).{0,24}\b(score|rating)\b|"
    r"\b(what'?s|what is|whats|how'?s|how is|tell me)\b.{0,32}\b(the )?(rating|score)\b"
    r")",
    re.I,
)
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
SHOW_SCORE_PART_LABELS = {
    "artist": "Artist",
    "hot": "Heat",
    "venue": "Room",
    "timing": "Timing",
}
SPOTIFY_ORDINALS = {
    "1": 0, "first": 0, "the first": 0, "the first one": 0,
    "2": 1, "second": 1, "the second": 1, "the second one": 1,
    "3": 2, "third": 2, "the third": 2, "the third one": 2,
}
MAX_HISTORY = 12
MAX_TOOL_ROUNDS = 4
MAX_SMS_CHARS = 1500
HISTORY_TTL = timedelta(hours=24)
PLACE_CACHE_TTL = timedelta(seconds=60)
ARTIST_HEAT_LIMIT = 12
INTRO_MESSAGE = "SproutMe keeps this chat for 24 hours. Text RESET anytime to start over."
US_TZ = ZoneInfo("America/Los_Angeles")
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
DATE_WORDS_RE = re.compile(
    r"\b(tonight|today|this evening|tomorrow|this weekend|this week|"
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
- Reply like a person texting, not a dashboard. One short spoken sentence that answers THEIR ask (these are the strongest matches). Then a blank line and the cards. Do not prefix cards with Name/Room/Hot or dump numbers — except when they ask for the rating/score of a show.
- If they ask the rating, score, SproutMe score, or why a show ranked: call explain_show_score and copy `sms`. That reply is the SproutMe number plus a short Artist / Heat / Room breakdown. Never answer a show-rating question with Google venue reviews.
- lookup_venue and rank_venues are only for when they ask about a room or the best venues in a city. Do not invent reviews. Do not use them for "rating for this show".
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
- Always search with the texter's saved city unless they name a different one.
- Saved genres are a preference, not a hard filter. If they just ask for shows in a city, search that city. SproutMe score gives saved-genre matches a small boost, then other genres. Never say there are no shows if other genres have hits.
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

Tools: search_events, get_event, explain_show_score, lookup_artist, lookup_venue, rank_venues, lookup_context, get_profile, update_profile, list_favorites.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_events",
            "description": "Search EDM events by city, genre, artist, date, or max ticket price. Returns `data` already ranked by SproutMe score, plus preformatted `sms.shows` to copy. Do not look up Spotify here. Use explain_show_score for show ratings; lookup_venue/rank_venues only if they ask about a room.",
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Artist, venue, or free text. Omit if unsure of spelling."},
                    "city": {"type": "string"},
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
            "name": "explain_show_score",
            "description": "Explain SproutMe's show score: overall number plus Artist / Heat / Room parts. Use when they ask the rating or score for a show (this show, the first one, or by name). Do not use lookup_venue for that.",
            "parameters": {
                "type": "object",
                "properties": {
                    "which": {
                        "type": "string",
                        "description": "Optional: this, that, first, second, third, or an artist/show name from the recent recs.",
                    },
                    "event_id": {"type": "integer", "description": "Optional numeric event id from search_events."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_venue",
            "description": "Google notes for a club or venue: rating, review count, and a short summary. Use when they ask how a room is, about reviews, or if a venue is good. Never use this for 'rating for this show' or SproutMe scores — use explain_show_score. Do not invent reviews.",
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
            "name": "get_profile",
            "description": "Get this texter's saved name, cities, and genres.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_profile",
            "description": "Save the texter's name, cities, or genres.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "city_list": {"type": "array", "items": {"type": "string"}},
                    "genre_list": {"type": "array", "items": {"type": "string"}},
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
        spotify=None,
        list_venue_places=None,
        save_venue_place=None,
        list_artist_heat=None,
    ):
        self.openai_api_key = openai_api_key
        self.model = model or "gpt-4.1"
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
        if openai_api_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=openai_api_key)
            except ImportError:
                logger.error("openai package is not installed")

    def reply(self, phone_number, body):
        text = (body or "").strip()
        self._latest_user_text = text
        self._last_sms_pack = None
        self._spotify_card_sms = None
        if not text:
            return "Text me a city or genre and I'll find shows. Example: house in Seattle this weekend."

        lowered = text.lower()
        if lowered in STOP_WORDS:
            self._clear_conversation(phone_number)
            return "You're unsubscribed. Text this number again anytime to opt back in. Reply HELP for help."
        if lowered in RESET_WORDS:
            started_at = datetime.now(timezone.utc)
            self._persist_conversation(phone_number, [], started_at)
            return f"Chat cleared. {INTRO_MESSAGE} What city or genre?"
        if lowered in HELP_WORDS:
            return (
                "SproutMe finds EDM shows. Text a city, genre, or artist "
                "(try 'techno in Seattle'). Chat lasts 24 hours. Text RESET to start over. Reply STOP to opt out."
            )

        if not self._client:
            return "SproutMe SMS is not configured yet. Try the site for now: https://sproutme-please.com"

        try:
            user = self._ensure_user(phone_number)
            history, started_at, is_new = self._load_conversation(phone_number)

            venue_rank = self._try_venue_rank(text, history)
            if venue_rank:
                self._store_turn(phone_number, history, started_at, text, [venue_rank], None)
                return self._with_intro([venue_rank], is_new)

            show_rating = self._try_show_rating(text, history)
            if show_rating:
                self._store_turn(phone_number, history, started_at, text, [show_rating], None)
                return self._with_intro([show_rating], is_new)

            venue_reply = self._try_venue_followup(text, history)
            if venue_reply:
                self._store_turn(phone_number, history, started_at, text, [venue_reply], None)
                return self._with_intro([venue_reply], is_new)

            messages = [{"role": "system", "content": self._system_prompt(user)}]
            messages.extend(self._openai_history(history))
            messages.append({"role": "user", "content": text})
            reply = self._complete(phone_number, messages)
        except Exception as exc:
            logger.exception("SMS agent failed for %s", phone_number[-4:] if phone_number else "")
            err = str(exc).lower()
            if "insufficient_quota" in err or "credit_balance" in err:
                return "SproutMe SMS is paused until API credits are added. Use the site for now: https://sproutme-please.com"
            if "429" in err or "rate limit" in err:
                return "Too many texts right now. Try again in a minute?"
            return "I hit a snag looking that up. Try again in a minute?"

        parts = [reply[:MAX_SMS_CHARS]]
        self._store_turn(phone_number, history, started_at, text, parts, None)
        return self._with_intro(parts, is_new)

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

    def _load_conversation(self, phone_number):
        data = {}
        if self.get_conversation:
            result = self.get_conversation(phone_number) or {}
            data = result.get("data") or {}
        if not data:
            data = self._memory.get(phone_number) or {}
        started_at = self._as_dt(data.get("started_at")) or datetime.now(timezone.utc)
        messages = list(data.get("messages") or [])
        now = datetime.now(timezone.utc)
        if messages and now - started_at > HISTORY_TTL:
            started_at = now
            messages = []
        is_new = len(messages) == 0
        return messages, started_at, is_new

    def _persist_conversation(self, phone_number, messages, started_at):
        payload = {
            "messages": messages,
            "started_at": started_at.isoformat() if hasattr(started_at, "isoformat") else started_at,
        }
        self._memory[phone_number] = payload
        if self.save_conversation:
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

    def _store_turn(self, phone_number, history, started_at, user_text, parts, artists=None):
        history.append({"role": "user", "content": user_text})
        outbound = parts if isinstance(parts, (list, tuple)) else [parts]
        for index, part in enumerate(outbound):
            item = {"role": "assistant", "content": (part or "")[:MAX_SMS_CHARS]}
            if artists and index == len(outbound) - 1:
                item["spotify_artists"] = artists
            history.append(item)
        self._persist_conversation(phone_number, history[-MAX_HISTORY:], started_at)

    def _with_intro(self, parts, is_new):
        outbound = [(part or "")[:MAX_SMS_CHARS] for part in (parts if isinstance(parts, (list, tuple)) else [parts]) if part]
        if not outbound:
            return "I didn't catch that. Try a city or genre?"
        if is_new:
            outbound[0] = f"{INTRO_MESSAGE}\n\n{outbound[0]}"
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

    def _system_prompt(self, user):
        profile = "No saved profile yet."
        if user:
            name = user.get("name") or "unknown"
            cities = ", ".join(user.get("city_list") or []) or "none"
            genres = ", ".join(user.get("genre_list") or []) or "none"
            profile = f"Name: {name}. Cities: {cities}. Genres: {genres}."
        clock = self._clock()
        return (
            SYSTEM_PROMPT.format(
                now_display=clock["now_display"],
                today_long=clock["today_long"],
                today_iso=clock["today_iso"],
                today_slash=clock["today_slash"],
                tomorrow_iso=clock["tomorrow_iso"],
                weekend=clock["weekend"],
            )
            + f"\n\nCurrent texter: {profile}"
        )

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
        if re.search(r"\bthis weekend\b", lowered):
            start = max(today, clock["weekend_start"])
            end = clock["weekend_end"]
            if start > end:
                start = clock["weekend_start"] + timedelta(days=7)
                end = clock["weekend_end"] + timedelta(days=7)
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
        return clean_event_url(url or "")

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

    def _try_venue_followup(self, text, history):
        if SHOW_RATING_RE.search(text or ""):
            return None
        if not VENUE_ASK_RE.search(text or ""):
            return None
        if self._looks_like_new_search(text):
            return None
        query = self._venue_query_from_text(text, history)
        if not query:
            return None
        card = self._lookup_venue_card(query, self._guess_city(text, history))
        return (card or {}).get("sms")

    def _format_show_score_blurb(self, event, score, parts):
        name = self._sms_title(event.get("event_name") or "This show")
        total = display_score(score)
        bits = []
        for key in ("artist", "hot", "venue", "timing"):
            if key not in (parts or {}):
                continue
            try:
                value = float(parts[key])
            except (TypeError, ValueError):
                continue
            if key == "timing" and value <= 0:
                continue
            label = SHOW_SCORE_PART_LABELS.get(key) or key.title()
            bits.append(f"{label} {int(round(value * 100))}")
        line = f"{name}: SproutMe {total}"
        if bits:
            line += " — " + ", ".join(bits)
        return line + "."

    def _score_event_parts(self, event):
        if not event:
            return 0.0, {}, ""
        index = self._venue_index()
        try:
            heat = self._heat_index() or {}
        except Exception as exc:
            logger.warning("artist heat index failed: %s", exc)
            heat = {}
        place = match_place(index, event.get("venue") or "", event.get("city") or "")
        artists = self._show_artists([event])
        artist = artists[0] if artists else ""
        row = match_heat(heat, artist)
        score, parts = score_show(
            heat_popularity(row) if row else 0,
            heat_breakout(row) if row else None,
            venue_score(place) if place and place.get("place_id") else None,
        )
        return score, parts, artist

    def _recent_recommended_shows(self, history):
        shows = []
        day_re = re.compile(
            r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*:\s+(.+)$",
            re.I,
        )
        for item in reversed(history or []):
            if item.get("role") != "assistant":
                continue
            lines = [line.strip() for line in (item.get("content") or "").splitlines()]
            idx = 0
            while idx < len(lines):
                match = day_re.match(lines[idx] or "")
                if not match:
                    idx += 1
                    continue
                name = self._sms_title(match.group(2))
                venue = ""
                city = ""
                if idx + 1 < len(lines):
                    detail = lines[idx + 1]
                    if detail and "http" not in detail.lower() and not day_re.match(detail):
                        venue = self._sms_venue(detail.split(",")[0])
                        if "(" in detail and ")" in detail:
                            city_match = re.search(r"\(([^)]+)\)", detail)
                            if city_match:
                                city = city_match.group(1).strip()
                        elif "," in detail:
                            bits = [bit.strip() for bit in detail.split(",") if bit.strip()]
                            if len(bits) >= 2 and not bits[1].startswith("$"):
                                city = bits[1]
                if name:
                    shows.append({"event_name": name, "venue": venue, "city": city})
                idx += 1
            if shows:
                break
        return shows[:5]

    def _match_catalog_show(self, hint):
        hint = hint or {}
        name = (hint.get("event_name") or "").strip()
        venue = (hint.get("venue") or "").strip()
        city = (hint.get("city") or "").strip()
        if not name:
            return None
        name_l = name.lower()
        venue_l = venue.lower()
        city_l = city.lower()
        events = self._all_events() or []
        best = None
        best_score = 0.0
        for event in events:
            event_name = (event.get("event_name") or "").strip()
            if not event_name:
                continue
            event_l = event_name.lower()
            score = 0.0
            if event_l == name_l:
                score += 5.0
            elif name_l in event_l or event_l in name_l:
                score += 3.0
            else:
                ratio = SequenceMatcher(None, name_l, event_l).ratio()
                if ratio < 0.72:
                    continue
                score += ratio * 2.0
            event_venue = self._sms_venue(event.get("venue") or "").lower()
            if venue_l and event_venue:
                if venue_l == event_venue or venue_l in event_venue or event_venue in venue_l:
                    score += 2.0
            event_city = (event.get("city") or "").lower()
            if city_l and (city_l in event_city or city_l in (event.get("venue") or "").lower()):
                score += 0.5
            if score > best_score:
                best_score = score
                best = event
        return best if best_score >= 3.0 else None

    def _resolve_rated_show(self, text, history, which=None, event_id=None):
        if event_id is not None:
            try:
                event = compact_event(self.get_event(int(event_id)))
            except Exception:
                event = None
            if event:
                return event

        recent = self._recent_recommended_shows(history)
        raw = (which or text or "").strip()
        lowered = raw.lower().strip()
        ordinal_key = re.sub(r"[^a-z0-9 ]+", "", lowered)
        ordinal_key = re.sub(r"\s+", " ", ordinal_key).strip()
        for prefix in (
            "whats the rating for ",
            "what is the rating for ",
            "whats the score for ",
            "what is the score for ",
            "rating for ",
            "score for ",
            "the rating for ",
            "the score for ",
        ):
            if ordinal_key.startswith(prefix):
                ordinal_key = ordinal_key[len(prefix):].strip()
                break
        if ordinal_key in SPOTIFY_ORDINALS and recent:
            index = SPOTIFY_ORDINALS[ordinal_key]
            if 0 <= index < len(recent):
                matched = self._match_catalog_show(recent[index])
                if matched:
                    return matched
        if ordinal_key in {"this", "that", "this show", "that show", "this one", "that one", "the show", "the one"}:
            if recent:
                matched = self._match_catalog_show(recent[0])
                if matched:
                    return matched

        # Named artist/show from the recent list or free text.
        needle = which or ""
        if not needle:
            match = re.search(
                r"(?:rating|score)\s+(?:for|of|on)\s+(.+?)[\?!.]*$",
                text or "",
                re.I,
            )
            if match:
                needle = match.group(1).strip()
                needle = re.sub(r"^(this|that|the)\s+(show|one|gig|event)\b", "", needle, flags=re.I).strip()
        if needle:
            needle_l = needle.lower()
            for hint in recent:
                name = (hint.get("event_name") or "").lower()
                if needle_l in name or name in needle_l:
                    matched = self._match_catalog_show(hint)
                    if matched:
                        return matched
            matched = self._match_catalog_show({"event_name": needle, "venue": "", "city": self._guess_city(text, history)})
            if matched:
                return matched

        if recent:
            return self._match_catalog_show(recent[0])
        return None

    def _explain_show_score_card(self, text, history, which=None, event_id=None):
        event = self._resolve_rated_show(text, history, which=which, event_id=event_id)
        if not event:
            return {
                "error": "no_show",
                "sms": "Tell me which show — or ask after I recommend one.",
            }
        score, parts, artist = self._score_event_parts(event)
        sms = self._format_show_score_blurb(event, score, parts)
        return {
            "event_id": event.get("id"),
            "event_name": event.get("event_name"),
            "artist": artist,
            "venue": event.get("venue"),
            "sprout_score": display_score(score),
            "sprout_parts": parts,
            "sms": sms,
        }

    def _try_show_rating(self, text, history):
        raw = (text or "").strip()
        if not raw or not SHOW_RATING_RE.search(raw):
            return None
        if VENUE_RANK_RE.search(raw) or VENUE_RANK_FOLLOW_RE.match(raw):
            return None
        card = self._explain_show_score_card(raw, history)
        return (card or {}).get("sms")

    def _join_show_blocks(self, blocks):
        return "\n\n".join(block.strip() for block in blocks if block and block.strip())

    def _compose_sms_reply(self, model_text, pack):
        pack = pack or {}
        shows = pack.get("shows") or []
        later = pack.get("later") or []
        place = pack.get("place") or "that city"
        if not shows and not later:
            return (model_text or "").strip() or f"No matching shows found in {place}."

        opener = (pack.get("opener") or "").strip()
        if model_text:
            first = model_text.strip().splitlines()[0].strip().rstrip(":")
            looks_like_show = bool(re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b", first, re.I))
            labeled = bool(re.match(r"^(biggest name|best room|heating up|soonest)\b", first, re.I))
            fluff = bool(re.match(
                r"^(here are|here's|a few|some |try these|found |i found|check these|listen:|want to check|want any)\b",
                first,
                re.I,
            ))
            blocked = any(first and first in block for block in shows + later)
            if (
                first
                and 12 <= len(first) <= 160
                and "http" not in first.lower()
                and not looks_like_show
                and not labeled
                and not fluff
                and not blocked
            ):
                opener = first

        if shows:
            body = self._join_show_blocks(shows[:3])
            if later and pack.get("wanted_day") and len(shows) < 3:
                body = f"{body}\n\nNext:\n{later[0]}"
        else:
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
        if self._name_mentions_artist(event.get("event_name"), query):
            return True
        if self._name_mentions_artist(event.get("venue"), query):
            return True
        return self._name_mentions_artist(event.get("organizer"), query)

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
            packed = compact_event(event)
            if packed and self._name_mentions_artist(packed.get("event_name"), needle):
                hits.append(packed)
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
        saved_cities = profile.get("city_list") or []
        saved_genres = profile.get("genre_list") or []
        city = (arguments.get("city") or "").strip() or (saved_cities[0] if saved_cities else None)
        explicit_genre = self._clean_label(arguments.get("genre") or "")
        query = arguments.get("q")
        if query:
            query = re.sub(r"\$\s*\d+(?:\.\d+)?", " ", query)
            query = re.sub(r"\b\d+\s*(bucks?|dollars?)\b", " ", query, flags=re.I)
            query = re.sub(r"\s+", " ", query).strip() or None
        date = arguments.get("date")
        latest = self._latest_user_text or ""
        if date and not self._message_names_a_day(latest):
            date = None
        wanted_start, wanted_end = self._parse_date_window(latest)
        if wanted_start is None:
            wanted_start, wanted_end = self._parse_date_window(date)
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
                if soonest_first:
                    ranked.append((preferred, day, price_rank[0], price_rank[1], tie, event))
                else:
                    ranked.append((preferred, price_rank[0], price_rank[1], day, tie, event))
            ranked.sort()
            return ranked

        soonest = self._message_names_a_day(latest)
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
        take = min(limit, 3)

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

        summary = self._search_summary(
            city=city,
            genre=explicit_genre,
            wanted_day=wanted_start,
            data=data,
            later=later,
            genre_relaxed=genre_relaxed,
            wanted_label=self._human_window(wanted_start, wanted_end),
            query=query if query_missed else None,
        )
        sms_shows = [self._format_sms_show(event) for event in data[:3]]
        sms_later = [self._format_sms_show(event) for event in later[:2]]
        artists = self._show_artists(data[:3] or later[:2])
        opener = self._mix_talk(city, explicit_genre, wanted_window or wanted_day, picks)
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
            "place": city or "that city",
            "wanted_day": applied_date,
            "opener": opener,
            "picks": picks,
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
                "genre": explicit_genre or None,
                "preferred_genres": saved_genres if not explicit_genre else [],
                "q": None if query_missed else used_query,
                "q_missed": query_missed,
                "date": applied_date,
                "max_price": max_price,
                "today": today.isoformat(),
                "unpriced_are_backups": bool(max_price is not None),
                "genre_relaxed": genre_relaxed,
                "unranked": any(row.get("why") == "unranked" for row in picked),
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
            for artist in headliners_for_event(event, limit=1):
                key = artist.lower()
                if key in seen:
                    continue
                seen.add(key)
                artists.append(artist)
                if len(artists) >= 3:
                    return artists
        return artists

    def _ensure_user(self, phone_number):
        result = self.get_user(phone_number) or {}
        if result.get("success") and result.get("data"):
            return result["data"]
        created = self.create_user(phone_number) or {}
        return created.get("data")

    def _complete(self, phone_number, messages):
        for _ in range(MAX_TOOL_ROUNDS + 1):
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.4,
            )
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
        if not city:
            profile = self._profile_data(phone_number)
            saved = profile.get("city_list") or []
            city = saved[0] if saved else ""
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

            if name == "explain_show_score":
                history, _started_at, _is_new = self._load_conversation(phone_number)
                card = self._explain_show_score_card(
                    self._latest_user_text or "",
                    history,
                    which=arguments.get("which") or arguments.get("q") or arguments.get("show"),
                    event_id=arguments.get("event_id"),
                )
                return json.dumps(card, default=str)

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

            if name == "lookup_context":
                card = lookup_context(arguments.get("q") or arguments.get("query") or arguments.get("artist") or "")
                return json.dumps(card or {"found": False}, default=str)

            if name == "get_profile":
                result = self.get_user(phone_number) or {}
                data = result.get("data") or {}
                return json.dumps({
                    "name": data.get("name"),
                    "city_list": data.get("city_list") or [],
                    "genre_list": data.get("genre_list") or [],
                })

            if name == "update_profile":
                updates = {}
                if arguments.get("name"):
                    self.update_name(phone_number, arguments["name"])
                    updates["name"] = arguments["name"]
                if arguments.get("city_list") is not None:
                    self.update_cities(phone_number, arguments["city_list"])
                    updates["city_list"] = arguments["city_list"]
                if arguments.get("genre_list") is not None:
                    self.update_genres(phone_number, arguments["genre_list"])
                    updates["genre_list"] = arguments["genre_list"]
                return json.dumps({"updated": updates})

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
