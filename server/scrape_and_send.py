#!/usr/bin/env python3.10
import hashlib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

try:
    from supabase import create_client
except ImportError:
    # A local ./supabase SQL folder can shadow the installed package.
    sys.modules.pop("supabase", None)
    _here = Path(__file__).resolve().parent if "__file__" in globals() else None
    if _here:
        sys.path = [p for p in sys.path if Path(p).resolve() != _here]
    from supabase import create_client


def _load_local_env():
    roots = []
    here = Path(__file__).resolve().parent
    roots.append(here / ".env")
    roots.append(here.parent / ".env")
    roots.extend((
        Path("/home/phelpsm4/sproutMe/.env"),
        Path("/home/phelpsm4/sproutMe/spotify.env"),
        Path("/home/phelpsm4/sproutMe/ticketmaster.env"),
        Path("/home/phelpsm4/sproutMe/places.env"),
    ))
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

try:
    from services.public_api import clean_event_url
except ImportError:
    from public_api import clean_event_url

try:
    from services.catalog_normalize import (
        dedupe_event_records,
        normalize_event as catalog_normalize_event,
        normalize_genre_tags as catalog_normalize_genre_tags,
        parse_headliners as catalog_parse_headliners,
        sanitize_headliners,
        serialize_headliners as catalog_serialize_headliners,
    )
except ImportError:
    from catalog_normalize import (
        dedupe_event_records,
        normalize_event as catalog_normalize_event,
        normalize_genre_tags as catalog_normalize_genre_tags,
        parse_headliners as catalog_parse_headliners,
        sanitize_headliners,
        serialize_headliners as catalog_serialize_headliners,
    )
# Supabase configuration
SUPABASE_URL = os.environ.get("SUPABASE_URL") or ""
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or ""
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or ""
OPENAI_MODEL = os.environ.get("OPENAI_MODEL") or "gpt-4.1"
SCRAPE_OPENAI_MODEL = os.environ.get("SCRAPE_OPENAI_MODEL") or "gpt-4.1-nano"
GENRE_BATCH_SIZE = 20
URL_ENRICH_BATCH_SIZE = 3
PAGE_TEXT_CHARS = 3500
FETCH_WORKERS = 6
FETCH_TIMEOUT = 8
FALLBACK_GENRE = "electronic"
FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
SKIP_FETCH_HOSTS = (
    "instagram.com",
    "facebook.com",
    "fb.com",
    "fb.me",
    "m.facebook.com",
)
MISSING_GENRE_VALUES = {
    "",
    "-",
    ".",
    "n/a",
    "na",
    "none",
    "null",
    "tbd",
    "unknown",
    "unspecified",
    "no genre",
    "no genres",
    "no genre info",
    "nogenreinfo",
}
GENRE_LABEL_PROMPT = """You label electronic dance music events with genre tags.

For each event, return 1-4 short lowercase genre tags a raver would search for.
Prefer common tags such as: house, techno, dubstep, bass, drum and bass, trance, hard techno, hardstyle, garage, disco, breaks, jungle, riddim, trap, afro house, melodic techno, psytrance.

Rules:
- Prefer the clean `headliner` artist name when present; use event_name as backup context.
- Never use none, n/a, unknown, tbd, empty, or "no genre info".
- If the listing omitted genre, infer from the headliner/artists, event name, venue, city, and organizer.
- If you are unsure, pick the closest electronic family rather than leaving it blank.
- If it does not look electronic, still pick the closest dance/electronic tags.

Return JSON only in this shape:
{"labels": [{"i": 0, "genre": "house, techno"}, {"i": 1, "genre": "dubstep"}]}
"""
FIELD_ENRICH_PROMPT = """You extract missing EDM event details from a listing, URL, and optional page text.

Only fill fields listed in "missing". Leave a field null if you do not have evidence.
ticket_info: a compact string such as "$25", "free", "$20 | 21+". Never invent a price. If page_text is empty, ticket_info must be null.
organizer: promoter/host/brand, not the city. URL slugs and event names are valid evidence.
venue: only if missing and clearly named.
genre: 1-4 lowercase tags. Never none, n/a, unknown, tbd, or empty.

Return JSON only:
{"fields": [{"i": 0, "ticket_info": "$20 | 21+", "organizer": "Insomniac", "venue": null, "genre": "house"}]}
"""
NORMALIZE_PROMPT = """You clean EDM listings into SproutMe's schema. Extract and normalize. Do not invent.

Rules:
- event_name: the show title. Keep artist names that are already in it. Strip " @ venue". Do not paraphrase or add hype.
- venue: venue name only, no city in parentheses, no leading @.
- city: one city (Seattle, Oakland, Austin). Never a mega-region like "Texas" or "Bay Area / Northern California" if a real city is in the venue.
- genre: 1-4 lowercase tags, comma-separated.
- ticket_info: compact "$25", "free", "$20 | 21+", or "$10 | 18+". Never invent a price or age. If unknown, null.
- organizer: promoter/host if present, else null.

Return JSON only:
{"events": [{"i": 0, "event_name": "Pier Play w/ Blond:ish", "venue": "Public Works", "city": "San Francisco", "genre": "house", "ticket_info": "$20 | 21+", "organizer": null}]}
"""
HEADLINER_PROMPT = """You extract performing artist/DJ names from messy EDM event titles.

People paste whatever into listings: party brands, tours, ages, cities, "w/", commas, b2b, presents, etc.
Your job is to return the actual billed acts as a JSON list.

Rules:
- Return artists only — not tour, year, venue, city, age (18+), or pure party/brand titles.
- An event can have multiple artists. Include every clearly billed act (max 3).
- "Bassvictim w/ Thoom" -> ["Bassvictim", "Thoom"]
- "Bassvictim, Thoom" -> ["Bassvictim", "Thoom"]
- "The Hellp, Bassvictim, DJ Chaotic Ugly" -> ["The Hellp", "Bassvictim", "DJ Chaotic Ugly"] (max 3: first three billed)
- "Charlotte de Witte presents KNTXT" -> ["Charlotte de Witte", "KNTXT"]
- "Pier Play w/ Blond:ish" -> ["Blond:ish"] (drop non-artist party brands)
- "Tinlicker North America 2026" -> ["Tinlicker"]
- "Artist A b2b Artist B" -> ["Artist A", "Artist B"]
- Festival / open decks / day party with no clear billed artist -> []
- Do not invent names. Keep punctuation like BUNT. or Blond:ish.

Return JSON only:
{"headliners":[{"i":0,"artists":["Bassvictim","Thoom"]},{"i":1,"artists":[]}]}
"""
NORMALIZE_BATCH_SIZE = 20
HEADLINER_BATCH_SIZE = 75
HEADLINER_LLM_WORKERS = 3
HEADLINER_JUNK_RE = re.compile(
    r"\b("
    r"20\d{2}|north america|south america|latin america|"
    r"europe|asia|australia|world\s*tour|tour|presents|"
    r"festival|fest\b|campout|day party|night party"
    r")\b",
    re.I,
)
MULTI_ACT_TITLE_RE = re.compile(
    r"(?:"
    r"\s+(?:w/|with|ft\.?|feat\.?|featuring|presents|b2b)\s+"
    r"|,|\s+[&+/|]\s+"
    r"|:\s+\S"
    r")",
    re.I,
)

class EventManager:
    def __init__(self):
        # Initialize Supabase client
        self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    def get_all_users(self):
        """Fetch all users from the database."""
        try:
            response = self.client.table('user_table').select('*').execute()
            return {
                "success": True,
                "message": "Users fetched successfully",
                "data": response.data
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching users: {str(e)}",
                "data": None
            }

    
    def get_all_phone_numbers(self):
        try:
            # Fetch all users
            users_response = self.get_all_users()
            
            # Check if the request was successful
            if not users_response["success"]:
                return {
                    "success": False,
                    "message": f"Error fetching users: {users_response['message']}",
                    "data": None
                }
            
            # Extract users from the response
            users = users_response["data"]
            
            # Extract phone numbers from each user
            phone_numbers = [user['phone_number'] for user in users]
            
            return {
                "success": True,
                "message": "Phone numbers fetched successfully",
                "data": phone_numbers
            }
        
        except Exception as e:
            return {
                "success": False,
                "message": f"Error fetching phone numbers: {str(e)}",
                "data": None
            }


class EventScraper:
    """
    A class to scrape upcoming events from 19hz.info and upload to Supabase
    """
    
    def __init__(self, supabase_url=None, supabase_key=None):
        """
        Initialize the scraper with the URL to scrape and Supabase credentials.
        
        Args:
            url (str): The URL of the event listing page.
            supabase_url (str, optional): Supabase project URL.
            supabase_key (str, optional): Supabase project API key.
        """
        self.urls = [
            "https://19hz.info/eventlisting_BayArea.php",
            "https://19hz.info/eventlisting_LosAngeles.php",
            "https://19hz.info/eventlisting_Seattle.php",
            "https://19hz.info/eventlisting_Atlanta.php",
            "https://19hz.info/eventlisting_Miami.php",
            "https://19hz.info/eventlisting_DC.php",
            "https://19hz.info/eventlisting_Texas.php",
            "https://19hz.info/eventlisting_Iowa.php",
            "https://19hz.info/eventlisting_Denver.php",
            "https://19hz.info/eventlisting_CHI.php",
            "https://19hz.info/eventlisting_Detroit.php",
            "https://19hz.info/eventlisting_Massachusetts.php",
            "https://19hz.info/eventlisting_LasVegas.php",
            "https://19hz.info/eventlisting_Phoenix.php",
            "https://19hz.info/eventlisting_BC.php",
            "https://19hz.info/eventlisting_ORE.php"
        ]
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.supabase_client = None
        
        # Initialize Supabase client if credentials are provided
        if supabase_url and supabase_key:
            self.init_supabase_client()
    
    def init_supabase_client(self, url=None, key=None):
        """
        Initialize the Supabase client.
        
        Args:
            url (str, optional): Supabase project URL. Defaults to self.supabase_url.
            key (str, optional): Supabase project API key. Defaults to self.supabase_key.
            
        Returns:
            bool: True if initialization was successful, False otherwise.
        """
        if url:
            self.supabase_url = url
        if key:
            self.supabase_key = key
            
        if not self.supabase_url or not self.supabase_key:
            print("Supabase URL and key are required.")
            return False
        
        try:
            self.supabase_client = create_client(self.supabase_url, self.supabase_key)
            return True
        except Exception as e:
            print(f"Failed to initialize Supabase client: {e}")
            return False

    def clear_table(self, table_name="Events_table"):
        """
        Delete all rows from the specified table.
        
        Args:
            table_name (str): Name of the Supabase table to clear.
            
        Returns:
            dict: Response from the Supabase API
        """
        if not self.supabase_client:
            return {
                "success": False,
                "message": "Supabase client not initialized. Call init_supabase_client first."
            }
            
        try:
            response = self.supabase_client.table(table_name).delete().neq("id", 10000000).execute()
            return {
                "success": True,
                "message": f"All rows deleted from {table_name}",
                "response": response
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error clearing table: {str(e)}"
            }
    
    def get_date_range(self, days=7):
        """
        Get today's date and a date X days from now.

        Args:
            days (int): Number of days to add to today's date.

        Returns:
            tuple: (today's date, future date) as datetime.date objects
        """
        today = datetime.today().date()
        future_date = today + timedelta(days=days)
        return today, future_date

    def scrape_upcoming_events(self):
        """
        Scrape events from multiple webpages with no date filtering.

        Returns:
            list: Event dicts from all city listing pages.
        """
        # Define mapping of URLs to city names
        url_to_city = {
            "https://19hz.info/eventlisting_BayArea.php": "San Francisco Bay Area / Northern California",
            "https://19hz.info/eventlisting_LosAngeles.php": "Los Angeles / Southern California",
            "https://19hz.info/eventlisting_Seattle.php": "Seattle",
            "https://19hz.info/eventlisting_Atlanta.php": "Atlanta",
            "https://19hz.info/eventlisting_Miami.php": "Miami",
            "https://19hz.info/eventlisting_DC.php": "Washington, DC / Maryland / Virginia",
            "https://19hz.info/eventlisting_Texas.php": "Texas",
            "https://19hz.info/eventlisting_Iowa.php": "Iowa / Nebraska",
            "https://19hz.info/eventlisting_Denver.php": "Denver",
            "https://19hz.info/eventlisting_CHI.php": "Chicago",
            "https://19hz.info/eventlisting_Detroit.php": "Detroit",
            "https://19hz.info/eventlisting_Massachusetts.php": "Massachusetts",
            "https://19hz.info/eventlisting_LasVegas.php": "Las Vegas",
            "https://19hz.info/eventlisting_Phoenix.php": "Phoenix",
            "https://19hz.info/eventlisting_BC.php": "Vancouver / British Columbia",
            "https://19hz.info/eventlisting_ORE.php":"Portland / Oregon",
        }

        import requests
        from bs4 import BeautifulSoup

        all_data = []  # List to store event data from all URLs

        # Iterate over all URLs
        for url in self.urls:
            try:
                response = requests.get(url)
                soup = BeautifulSoup(response.text, 'html.parser')

                # Find the tbody element
                tbody = soup.find('tbody')
                if not tbody:
                    print(f"No tbody found on the page: {url}")
                    continue  # Skip to the next URL

                # Find all rows directly under tbody
                rows = tbody.find_all('tr', recursive=False)

                # Process each row
                for row in rows:
                    event_data = self._extract_event_data(row)
                    if event_data and event_data["raw_date"]:
                        # Add city to event data
                        event_data["city"] = url_to_city.get(url, "Unknown")
                        all_data.append(event_data)

            except Exception as e:
                print(f"Error scraping {url}: {e}")

        return all_data

    def _extract_event_data(self, row):
        """
        Extract data from a table row.
        
        Args:
            row (bs4.element.Tag): BeautifulSoup Tag containing a table row.
            
        Returns:
            dict: Dictionary with event data or None if row is invalid.
        """
        # Extract data from each cell
        cells = row.find_all('td')
        
        # Skip if we don't have enough cells
        if len(cells) < 5:
            return None
        
        # Extract date
        date = cells[0].text.strip() if cells[0] else "No date"
        
        # Get event name and venue
        event_cell = cells[1] if len(cells) > 1 else None
        event_link = event_cell.find('a') if event_cell else None
        event_name = event_link.text.strip() if event_link else "No event name"
        event_url = event_link['href'] if event_link and 'href' in event_link.attrs else "No URL"
        
        venue_text = event_cell.text.strip() if event_cell else ""
        rest = venue_text
        if event_name and rest.startswith(event_name):
            rest = rest[len(event_name):].strip()
        rest = re.sub(r"^@\s*", "", rest).strip()
        name, city = self._split_venue_city(rest, "")
        if name and city:
            venue = f"{name} ({city})"
        else:
            venue = name or rest or "Venue not found"
        
        # Get genre from 19hz when the lister filled it in; leave blank otherwise.
        genre = cells[2].text.strip() if len(cells) > 2 else ""
        
        # Get ticket info
        ticket_info = cells[3].text.strip() if len(cells) > 3 else ""
        
        # Get organizer info (if available)
        organizer = cells[4].text.strip() if len(cells) > 4 else ""
        
        # Event link (might be Facebook or Instagram)
        event_link_cell = cells[5] if len(cells) > 5 else None
        event_link_a = event_link_cell.find('a') if event_link_cell else None
        event_link_url = event_link_a['href'] if event_link_a and 'href' in event_link_a.attrs else "No event link"
        event_link_text = event_link_a.text.strip() if event_link_a else ""
        
        # Date in the last cell (if available)
        date_raw = ""
        if len(cells) > 6 and cells[6].find('div', class_='shrink'):
            date_raw = cells[6].find('div', class_='shrink').text.strip()
        
        return {
            "date": date,
            "event_name": event_name,
            "event_url": event_url,
            "venue": venue,
            "genre": genre,
            "ticket_info": ticket_info,
            "organizer": organizer,
            "event_link_url": event_link_url,
            "event_link_text": event_link_text,
            "raw_date": date_raw,
            "_source": {
                "event_name": event_name,
                "venue": venue,
                "raw_date": date_raw or date,
            },
        }

    def genre_is_missing(self, genre):
        if genre is None:
            return True
        if isinstance(genre, float) and genre != genre:
            return True
        cleaned = re.sub(r"\s+", " ", str(genre).strip().lower())
        compact = cleaned.replace(" ", "")
        return cleaned in MISSING_GENRE_VALUES or compact in MISSING_GENRE_VALUES

    def _normalize_genre_tags(self, genre):
        return catalog_normalize_genre_tags(genre)

    def _genre_fingerprint(self, rec):
        source = rec.get("_source") if isinstance(rec.get("_source"), dict) else {}
        key = "|".join([
            (source.get("event_name") or rec.get("event_name") or "").strip().lower(),
            (source.get("venue") or rec.get("venue") or "").strip().lower(),
            (source.get("raw_date") or rec.get("raw_date") or rec.get("date") or "").strip().lower(),
        ])
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _is_missing_text(self, value, extra=()):
        if value is None:
            return True
        if isinstance(value, float) and value != value:
            return True
        cleaned = re.sub(r"\s+", " ", str(value).strip().lower())
        placeholders = MISSING_GENRE_VALUES | {item.lower() for item in extra}
        return cleaned in placeholders or cleaned.replace(" ", "") in placeholders

    def _clean_text(self, value):
        text = unescape(re.sub(r"\s+", " ", str(value or "").strip()))
        if self._is_missing_text(text, ("no ticket info", "no organizer info", "venue not found", "no url", "no event link")):
            return ""
        return text

    def _missing_fields(self, rec, fields=None):
        fields = fields or ("genre", "ticket_info", "organizer", "venue")
        missing = []
        for field in fields:
            if field == "genre" and self.genre_is_missing(rec.get("genre")):
                missing.append(field)
            elif field == "ticket_info" and self._is_missing_text(rec.get("ticket_info"), ("no ticket info",)):
                missing.append(field)
            elif field == "organizer" and self._is_missing_text(rec.get("organizer"), ("no organizer info",)):
                missing.append(field)
            elif field == "venue" and self._is_missing_text(rec.get("venue"), ("venue not found",)):
                missing.append(field)
        return missing

    def _unwrap_url(self, url):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for key in ("u", "url", "redirect"):
            candidates = query.get(key) or []
            if candidates:
                inner = unquote(candidates[0])
                if inner.startswith("http"):
                    return inner
        return url

    def _usable_urls(self, rec):
        urls = []
        for key in ("event_url", "event_link_url"):
            raw = rec.get(key)
            if self._is_missing_text(raw, ("no url", "no event link")):
                continue
            url = self._unwrap_url(str(raw).strip())
            if url.startswith("http"):
                urls.append(url)
        return list(dict.fromkeys(urls))

    def _skip_fetch(self, url):
        host = (urlparse(url).hostname or "").lower()
        return any(host == blocked or host.endswith("." + blocked) for blocked in SKIP_FETCH_HOSTS)

    def _preferred_event_url(self, rec):
        urls = self._usable_urls(rec)
        if not urls:
            return ""
        external = [url for url in urls if "19hz.info" not in url.lower()]
        return (external or urls)[0]

    def _region_city(self, city):
        try:
            from services.catalog_normalize import is_region_city
        except ImportError:
            from catalog_normalize import is_region_city
        return is_region_city(city)

    def _city_from_paren(self, raw):
        city = self._clean_text(raw).split(",")[0].split("/")[0].strip()
        if not city or len(city) > 40:
            return ""
        if re.search(r"\d+\+|all ages|capacity|\b20\d{2}\b", city, re.I):
            return ""
        return city

    def _venue_is_mashed(self, venue):
        text = venue or ""
        if re.search(r"\)[A-Za-z0-9$]", text):
            return True
        if re.search(r"\$\s*\d|\b\d{2}\+|20\d{2}\s*/|\b(?:facebook|instagram) page\b", text, re.I):
            return True
        return len(text) > 80

    def _split_venue_city(self, venue, listing_city=""):
        text = self._clean_text(venue)
        name = text
        city = ""
        match = re.search(r"^(.*?)\s*\(([^)]+)\)", text)
        if match:
            peeled = self._clean_text(match.group(1))
            parsed_city = self._city_from_paren(match.group(2))
            if peeled:
                name = peeled
            if parsed_city:
                city = parsed_city
        name = re.split(
            r"(?:\$\s*\d|20\d{2}\s*/|\b(?:facebook|instagram) page\b)",
            name,
            maxsplit=1,
            flags=re.I,
        )[0].strip(" ,;-@")
        if not city:
            city = self._clean_text((listing_city or "").split("/")[0])
        return name, city

    def _compact_ticket_info(self, ticket_info):
        text = self._clean_text(ticket_info)
        if not text:
            return ""
        lowered = text.lower()
        age = ""
        age_match = re.search(r"\b(18\+|21\+|16\+)", text)
        if age_match:
            age = age_match.group(1)
        if re.search(r"\bfree\b", lowered):
            price = "free"
        else:
            amounts = [match.replace(" ", "") for match in re.findall(r"\$\s*\d+(?:\.\d+)?", text)]
            price = amounts[0] if amounts else ""
            if len(text) > 22 and not price:
                return text
        if not price and not age:
            return text
        return " | ".join(part for part in (price, age) if part)

    def _safe_event_name(self, original, proposed):
        original = self._clean_text(original)
        proposed = self._clean_text(proposed)
        if not proposed:
            return original
        if not original:
            return proposed
        if proposed.lower() == original.lower():
            return proposed
        if proposed.lower() in original.lower() or original.lower() in proposed.lower():
            return proposed
        from difflib import SequenceMatcher
        if SequenceMatcher(None, original.lower(), proposed.lower()).ratio() >= 0.55:
            return proposed
        return original

    def _format_venue_with_city(self, venue, city):
        name, parsed_city = self._split_venue_city(venue, city)
        city = parsed_city or self._clean_text(city)
        if name and city and f"({city.lower()})" not in name.lower():
            return f"{name} ({city})"
        return name or venue

    def _clean_cached_venue(self, venue):
        name, city = self._split_venue_city(venue, "")
        return self._format_venue_with_city(name or venue, city)

    def _shape_record(self, rec):
        if not rec.get("_source"):
            rec["_source"] = {
                "event_name": rec.get("event_name") or "",
                "venue": rec.get("venue") or "",
                "raw_date": rec.get("raw_date") or rec.get("date") or "",
            }
        rec["event_name"] = self._clean_text(rec.get("event_name"))
        rec["organizer"] = self._clean_text(rec.get("organizer"))
        rec["genre"] = self._normalize_genre_tags(rec.get("genre"))
        rec["ticket_info"] = self._compact_ticket_info(rec.get("ticket_info"))
        venue_name, venue_city = self._split_venue_city(rec.get("venue") or "", rec.get("city") or "")
        city = venue_city or self._clean_text(rec.get("city"))
        if venue_city and self._region_city(rec.get("city") or ""):
            city = venue_city
        rec["city"] = city
        rec["venue"] = self._format_venue_with_city(venue_name or rec.get("venue"), rec["city"])
        preferred = self._preferred_event_url(rec)
        if preferred:
            rec["event_url"] = preferred
        rec["event_url"] = clean_event_url(rec.get("event_url") or "")
        rec["event_link_url"] = clean_event_url(self._clean_text(rec.get("event_link_url")))
        rec["event_link_text"] = self._clean_text(rec.get("event_link_text"))
        rec["date"] = self._clean_text(rec.get("date"))
        rec["raw_date"] = self._clean_text(rec.get("raw_date") or rec.get("date"))
        catalog_normalize_event(rec)
        return rec

    def _needs_normalize(self, rec):
        if rec.get("_skip_enrich"):
            return False
        name = rec.get("event_name") or ""
        city = rec.get("city") or ""
        venue = rec.get("venue") or ""
        ticket = rec.get("ticket_info") or ""
        if " @ " in name or name.lower() in {"", "no event name"}:
            return True
        if self._region_city(city):
            return True
        if self._is_missing_text(venue, ("venue not found",)):
            return True
        if self._venue_is_mashed(venue):
            return True
        if len(ticket) > 28:
            return True
        return False

    def _lookup_cached_genres(self, records):
        cached = {}
        fingerprints = [self._genre_fingerprint(rec) for rec in records]
        select_cols = "fingerprint,event_name,genre,ticket_info,organizer,venue,source_url,city,headliner"
        fallback_cols = "fingerprint,event_name,genre,ticket_info,organizer,venue,source_url"
        for start in range(0, len(fingerprints), 100):
            chunk = fingerprints[start:start + 100]
            rows = []
            try:
                response = (
                    self.supabase_client.table("event_genre_cache")
                    .select(select_cols)
                    .in_("fingerprint", chunk)
                    .execute()
                )
                rows = response.data or []
            except Exception as e:
                # Pre-migration cache without city/headliner columns.
                if "city" in str(e) or "headliner" in str(e) or "42703" in str(e):
                    try:
                        response = (
                            self.supabase_client.table("event_genre_cache")
                            .select(fallback_cols)
                            .in_("fingerprint", chunk)
                            .execute()
                        )
                        rows = response.data or []
                    except Exception as retry_error:
                        print(f"Field cache lookup failed: {retry_error}")
                        continue
                else:
                    print(f"Field cache lookup failed: {e}")
                    continue
            for row in rows:
                cached[row["fingerprint"]] = {
                    "event_name": self._clean_text(row.get("event_name")),
                    "genre": self._normalize_genre_tags(row.get("genre")),
                    "ticket_info": self._clean_text(row.get("ticket_info")),
                    "organizer": self._clean_text(row.get("organizer")),
                    "venue": self._clean_text(row.get("venue")),
                    "source_url": self._clean_text(row.get("source_url")),
                    "city": self._clean_text(row.get("city")),
                    "headliner": self._clean_text(row.get("headliner")),
                }
        return cached
    def _apply_cached_fields(self, rec, cached_row):
        if not cached_row:
            return False
        applied = False
        if self.genre_is_missing(rec.get("genre")) and cached_row.get("genre"):
            rec["genre"] = cached_row["genre"]
            applied = True
        if "ticket_info" in self._missing_fields(rec, ("ticket_info",)) and cached_row.get("ticket_info"):
            rec["ticket_info"] = cached_row["ticket_info"]
            applied = True
        if "organizer" in self._missing_fields(rec, ("organizer",)) and cached_row.get("organizer"):
            rec["organizer"] = cached_row["organizer"]
            applied = True
        if "venue" in self._missing_fields(rec, ("venue",)) and cached_row.get("venue"):
            rec["venue"] = self._clean_cached_venue(cached_row["venue"])
            applied = True
        if (not self._clean_text(rec.get("city")) or self._region_city(rec.get("city") or "")) and cached_row.get("city"):
            if not self._region_city(cached_row["city"]):
                rec["city"] = cached_row["city"]
                applied = True
        if not self._parse_artists_field(rec.get("headliner")) and cached_row.get("headliner"):
            artists = self._parse_artists_field(cached_row["headliner"])
            if artists:
                rec["headliner"] = self._serialize_artists(artists)
                applied = True
        if applied:
            catalog_normalize_event(rec)
        return applied

    def _save_cached_genres(self, records):
        rows = []
        seen = set()
        for rec in records:
            genre = self._normalize_genre_tags(rec.get("genre"))
            ticket_info = self._clean_text(rec.get("ticket_info"))
            organizer = self._clean_text(rec.get("organizer"))
            venue = self._clean_cached_venue(rec.get("venue"))
            city = self._clean_text(rec.get("city"))
            headliner = self._serialize_artists(self._parse_artists_field(rec.get("headliner")))
            if not any([genre, ticket_info, organizer, venue, city, headliner]):
                continue
            fingerprint = self._genre_fingerprint(rec)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append({
                "fingerprint": fingerprint,
                "event_name": rec.get("event_name") or "",
                "venue": venue or rec.get("venue") or "",
                "genre": genre,
                "ticket_info": ticket_info,
                "organizer": organizer,
                "source_url": rec.get("event_url") or rec.get("event_link_url") or "",
                "city": city,
                "headliner": headliner,
            })
        for start in range(0, len(rows), 100):
            chunk = rows[start:start + 100]
            try:
                self.supabase_client.table("event_genre_cache").upsert(chunk).execute()
            except Exception as e:
                # Retry without new columns if migration not applied yet.
                if "city" in str(e) or "headliner" in str(e) or "42703" in str(e):
                    slim = [
                        {k: v for k, v in row.items() if k not in ("city", "headliner")}
                        for row in chunk
                    ]
                    try:
                        self.supabase_client.table("event_genre_cache").upsert(slim).execute()
                        continue
                    except Exception as retry_error:
                        print(f"Field cache save failed: {retry_error}")
                        continue
                print(f"Field cache save failed: {e}")
    def _openai_chat(self, messages):
        model = SCRAPE_OPENAI_MODEL
        payload = {
            "model": model,
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        if not str(model).startswith("gpt-5"):
            payload["temperature"] = 0
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            response = client.chat.completions.create(**payload)
            return response.choices[0].message.content
        except Exception as sdk_error:
            print(f"OpenAI SDK failed ({sdk_error}); using HTTPS fallback")
            request = Request(
                "https://api.openai.com/v1/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=90) as response:
                    data = json.loads(response.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
            except (HTTPError, URLError, KeyError, json.JSONDecodeError) as http_error:
                raise RuntimeError(f"OpenAI request failed: {http_error}") from http_error

    def _parse_genre_labels(self, content, batch_size):
        text = (content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            parsed = json.loads(match.group(0)) if match else {}
        labels = parsed.get("labels") if isinstance(parsed, dict) else parsed
        mapped = {}
        if isinstance(labels, dict):
            labels = [{"i": key, "genre": value} for key, value in labels.items()]
        if not isinstance(labels, list):
            return mapped
        for item in labels:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("i", item.get("index")))
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= batch_size:
                continue
            genre = self._normalize_genre_tags(item.get("genre") or item.get("tags") or "")
            if genre:
                mapped[index] = genre
        return mapped

    def _label_genre_batch(self, batch):
        payload = []
        for index, rec in enumerate(batch):
            payload.append({
                "i": index,
                "headliner": rec.get("headliner") or "",
                "event_name": rec.get("event_name") or "",
                "venue": rec.get("venue") or "",
                "city": rec.get("city") or "",
                "organizer": rec.get("organizer") or "",
                "event_url": rec.get("event_url") or "",
                "ticket_info": rec.get("ticket_info") or "",
            })
        content = self._openai_chat([
            {"role": "system", "content": GENRE_LABEL_PROMPT},
            {"role": "user", "content": json.dumps({"events": payload})},
        ])
        return self._parse_genre_labels(content, len(batch))

    def _json_ld_items(self, html):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        items = []
        for script in soup.find_all("script"):
            script_type = " ".join(script.get("type") or []).lower() if isinstance(script.get("type"), list) else str(script.get("type") or "").lower()
            if "ld+json" not in script_type:
                continue
            raw = (script.string or script.get_text() or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            queue = data if isinstance(data, list) else [data]
            while queue:
                item = queue.pop(0)
                if not isinstance(item, dict):
                    continue
                if isinstance(item.get("@graph"), list):
                    queue.extend(item["@graph"])
                items.append(item)
        return items

    def _json_ld_name(self, value):
        if isinstance(value, str):
            return self._clean_text(value)
        if isinstance(value, dict):
            return self._clean_text(value.get("name") or value.get("legalName") or "")
        if isinstance(value, list):
            for item in value:
                name = self._json_ld_name(item)
                if name:
                    return name
        return ""

    def _format_price(self, amount, currency="USD"):
        try:
            number = float(str(amount).replace(",", ""))
        except (TypeError, ValueError):
            return ""
        if number <= 0:
            return "free"
        if float(number).is_integer():
            amount_text = str(int(number))
        else:
            amount_text = f"{number:.2f}".rstrip("0").rstrip(".")
        if str(currency or "USD").upper() in ("USD", "US", ""):
            return f"${amount_text}"
        return f"{amount_text} {currency}"

    def _extract_structured_fields(self, html):
        extracted = {}
        for item in self._json_ld_items(html):
            types = item.get("@type")
            type_names = types if isinstance(types, list) else [types]
            type_names = [str(name or "").lower() for name in type_names]
            if not any("event" in name for name in type_names):
                continue
            organizer = self._json_ld_name(item.get("organizer") or item.get("performer"))
            if organizer:
                extracted["organizer"] = organizer
            venue = self._json_ld_name((item.get("location") or {}) if not isinstance(item.get("location"), list) else (item.get("location") or [None])[0])
            if not venue:
                location = item.get("location")
                if isinstance(location, list) and location:
                    venue = self._json_ld_name(location[0])
                else:
                    venue = self._json_ld_name(location)
            if venue:
                extracted["venue"] = venue
            if item.get("isAccessibleForFree") is True:
                extracted["ticket_info"] = "free"
            offers = item.get("offers")
            offer_list = offers if isinstance(offers, list) else [offers] if offers else []
            prices = []
            for offer in offer_list:
                if not isinstance(offer, dict):
                    continue
                if str(offer.get("availability") or "").endswith("SoldOut"):
                    continue
                price = self._format_price(offer.get("price") or offer.get("lowPrice"), offer.get("priceCurrency"))
                if price:
                    prices.append(price)
            if prices:
                extracted["ticket_info"] = prices[0]
        return extracted

    def _html_to_text(self, html):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        return re.sub(r"\s+", " ", soup.get_text(" ")).strip()[:PAGE_TEXT_CHARS]

    def _fetch_page(self, url):
        url = self._unwrap_url(url)
        if self._skip_fetch(url):
            return "", {}
        request = Request(url, headers=FETCH_HEADERS)
        try:
            with urlopen(request, timeout=FETCH_TIMEOUT) as response:
                raw = response.read(250000)
                content_type = (response.headers.get("Content-Type") or "").lower()
        except Exception as e:
            print(f"Event page fetch failed ({url[:80]}): {e}")
            return "", {}
        if "html" not in content_type and "json" not in content_type and content_type:
            return "", {}
        html = raw.decode("utf-8", errors="ignore")
        return self._html_to_text(html), self._extract_structured_fields(html)

    def _parse_field_labels(self, content, batch_size):
        text = (content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            parsed = json.loads(match.group(0)) if match else {}
        labels = parsed.get("fields") if isinstance(parsed, dict) else parsed
        mapped = {}
        if isinstance(labels, dict) and "i" not in labels:
            labels = [{"i": key, **(value if isinstance(value, dict) else {"organizer": value})} for key, value in labels.items()]
        if not isinstance(labels, list):
            return mapped
        for item in labels:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("i", item.get("index")))
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= batch_size:
                continue
            mapped[index] = {
                "ticket_info": self._clean_text(item.get("ticket_info")),
                "organizer": self._clean_text(item.get("organizer")),
                "venue": self._clean_text(item.get("venue")),
                "genre": self._normalize_genre_tags(item.get("genre") or ""),
            }
        return mapped

    def _label_missing_fields_batch(self, batch):
        payload = []
        for index, rec in enumerate(batch):
            payload.append({
                "i": index,
                "missing": rec.get("_missing_fields") or self._missing_fields(rec),
                "headliner": rec.get("headliner") or "",
                "event_name": rec.get("event_name") or "",
                "venue": rec.get("venue") or "",
                "city": rec.get("city") or "",
                "organizer": rec.get("organizer") or "",
                "ticket_info": rec.get("ticket_info") or "",
                "genre": rec.get("genre") or "",
                "event_url": (self._usable_urls(rec) or [""])[0],
                "page_text": rec.get("_page_text") or "",
            })
        content = self._openai_chat([
            {"role": "system", "content": FIELD_ENRICH_PROMPT},
            {"role": "user", "content": json.dumps({"events": payload})},
        ])
        return self._parse_field_labels(content, len(batch))

    def _apply_extracted_fields(self, rec, extracted, allowed=None):
        allowed = allowed or self._missing_fields(rec)
        changed = False
        if "ticket_info" in allowed and extracted.get("ticket_info"):
            rec["ticket_info"] = extracted["ticket_info"]
            changed = True
        if "organizer" in allowed and extracted.get("organizer"):
            rec["organizer"] = extracted["organizer"]
            changed = True
        if "venue" in allowed and extracted.get("venue"):
            rec["venue"] = extracted["venue"]
            changed = True
        if "genre" in allowed and extracted.get("genre"):
            rec["genre"] = extracted["genre"]
            changed = True
        return changed

    def _value_in_evidence(self, rec, value):
        value = self._clean_text(value)
        if not value:
            return False
        blob = " ".join([
            rec.get("event_name") or "",
            rec.get("venue") or "",
            rec.get("city") or "",
            rec.get("organizer") or "",
            rec.get("ticket_info") or "",
            " ".join(self._usable_urls(rec)),
            rec.get("_page_text") or "",
        ]).lower()
        lowered = value.lower()
        if lowered in blob:
            return True
        tokens = [token for token in re.split(r"[^a-z0-9]+", lowered) if len(token) > 2]
        return bool(tokens) and all(token in blob for token in tokens)

    def fill_missing_url_fields(self, records):
        """Fill ticket/organizer/venue (and leftover genre) from the event URL when one exists."""
        targets = []
        for rec in records:
            if rec.get("_skip_enrich"):
                continue
            missing = self._missing_fields(rec, ("ticket_info", "organizer", "venue", "genre"))
            url_fields = [field for field in missing if field != "genre"]
            if not url_fields:
                continue
            if not self._usable_urls(rec):
                continue
            rec["_missing_fields"] = missing
            targets.append(rec)
        if not targets:
            print("No missing ticket/organizer/venue fields with event URLs.")
            return records

        print(f"Enriching {len(targets)} events with missing fields from event URLs via {SCRAPE_OPENAI_MODEL}...")
        cached = self._lookup_cached_genres(targets) if self.supabase_client else {}
        remaining = []
        cache_hits = 0
        for rec in targets:
            if self._apply_cached_fields(rec, cached.get(self._genre_fingerprint(rec))):
                cache_hits += 1
            if self._missing_fields(rec, ("ticket_info", "organizer", "venue")):
                remaining.append(rec)
        print(f"URL-field cache hits: {cache_hits}. Pages to inspect: {len(remaining)}.")

        fetch_urls = {}
        for rec in remaining:
            fetch_urls[id(rec)] = self._usable_urls(rec)[0]
        unique_urls = list(dict.fromkeys(fetch_urls.values()))
        page_by_url = {}

        def fetch_one(url):
            return url, self._fetch_page(url)

        if unique_urls:
            with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
                futures = [pool.submit(fetch_one, url) for url in unique_urls]
                done = 0
                for future in as_completed(futures):
                    url, (text, structured) = future.result()
                    page_by_url[url] = (text, structured)
                    done += 1
                    if done % 50 == 0 or done == len(unique_urls):
                        print(f"Fetched {done}/{len(unique_urls)} event pages.")

        still_need_model = []
        structured_hits = 0
        for rec in remaining:
            url = fetch_urls[id(rec)]
            text, structured = page_by_url.get(url, ("", {}))
            rec["_page_text"] = text
            allowed = rec.get("_missing_fields") or self._missing_fields(rec)
            if structured and self._apply_extracted_fields(rec, structured, allowed):
                structured_hits += 1
            rec["_missing_fields"] = self._missing_fields(rec)
            missing = rec["_missing_fields"]
            if not missing:
                continue
            if missing == ["ticket_info"] and not rec.get("_page_text"):
                continue
            still_need_model.append(rec)
        print(f"Structured page data filled {structured_hits} events. OpenAI URL extraction: {len(still_need_model)}.")

        labeled_now = []
        for start in range(0, len(still_need_model), URL_ENRICH_BATCH_SIZE):
            batch = still_need_model[start:start + URL_ENRICH_BATCH_SIZE]
            labels = {}
            try:
                labels = self._label_missing_fields_batch(batch)
            except Exception as e:
                print(f"OpenAI URL-field batch failed, retrying once: {e}")
                time.sleep(2)
                try:
                    labels = self._label_missing_fields_batch(batch)
                except Exception as retry_error:
                    print(f"OpenAI URL-field batch failed again: {retry_error}")
            for offset, rec in enumerate(batch):
                extracted = labels.get(offset) or {}
                if not rec.get("_page_text"):
                    extracted["ticket_info"] = ""
                if extracted.get("organizer") and not self._value_in_evidence(rec, extracted["organizer"]):
                    extracted["organizer"] = ""
                if extracted.get("venue") and not self._value_in_evidence(rec, extracted["venue"]):
                    extracted["venue"] = ""
                if self._apply_extracted_fields(rec, extracted, rec.get("_missing_fields")):
                    labeled_now.append(rec)
            print(f"Extracted URL fields {min(start + len(batch), len(still_need_model))}/{len(still_need_model)}.")
            if start + URL_ENRICH_BATCH_SIZE < len(still_need_model):
                time.sleep(0.2)

        changed = labeled_now + [rec for rec in remaining if rec not in labeled_now and not self._missing_fields(rec, ("ticket_info", "organizer", "venue"))]
        if self.supabase_client and (changed or structured_hits):
            self._save_cached_genres(targets)
        for rec in targets:
            rec.pop("_page_text", None)
            rec.pop("_missing_fields", None)
        return records

    def _parse_normalized_events(self, content, batch_size):
        text = (content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            parsed = json.loads(match.group(0)) if match else {}
        labels = parsed.get("events") if isinstance(parsed, dict) else parsed
        mapped = {}
        if isinstance(labels, dict) and "i" not in labels:
            labels = [{"i": key, **(value if isinstance(value, dict) else {"event_name": value})} for key, value in labels.items()]
        if not isinstance(labels, list):
            return mapped
        for item in labels:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("i", item.get("index")))
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= batch_size:
                continue
            mapped[index] = {
                "event_name": self._clean_text(item.get("event_name")),
                "venue": self._clean_text(item.get("venue")),
                "city": self._clean_text(item.get("city")),
                "genre": self._normalize_genre_tags(item.get("genre") or ""),
                "ticket_info": self._compact_ticket_info(item.get("ticket_info")),
                "organizer": self._clean_text(item.get("organizer")),
            }
        return mapped

    def _label_normalize_batch(self, batch):
        payload = []
        for index, rec in enumerate(batch):
            source = rec.get("_source") or {}
            payload.append({
                "i": index,
                "headliner": rec.get("headliner") or "",
                "event_name": rec.get("event_name") or source.get("event_name") or "",
                "venue": rec.get("venue") or "",
                "city": rec.get("city") or "",
                "organizer": rec.get("organizer") or "",
                "ticket_info": rec.get("ticket_info") or "",
                "genre": rec.get("genre") or "",
            })
        content = self._openai_chat([
            {"role": "system", "content": NORMALIZE_PROMPT},
            {"role": "user", "content": json.dumps({"events": payload})},
        ])
        return self._parse_normalized_events(content, len(batch))

    def _ticket_price_invented(self, original, proposed):
        proposed_text = (proposed or "").lower()
        original_text = (original or "").lower()
        if not proposed:
            return True
        proposed_amounts = set(re.findall(r"\$\s*\d+", proposed_text))
        original_amounts = set(re.findall(r"\$\s*\d+", original_text))
        if proposed_amounts and not original_amounts and "free" not in original_text:
            return True
        if re.search(r"\bfree\b", proposed_text) and original and "free" not in original_text and not original_amounts:
            return True
        return False

    def _apply_normalized_fields(self, rec, extracted):
        changed = False
        if extracted.get("event_name"):
            safe = self._safe_event_name(rec.get("event_name"), extracted["event_name"])
            if safe and safe != rec.get("event_name"):
                rec["event_name"] = safe
                changed = True
        if extracted.get("venue") and (
            self._is_missing_text(rec.get("venue"), ("venue not found",))
            or self._value_in_evidence(rec, extracted["venue"])
            or extracted["venue"].lower() in (rec.get("venue") or "").lower()
        ):
            rec["venue"] = extracted["venue"]
            changed = True
        if extracted.get("city") and not self._region_city(extracted["city"]):
            rec["city"] = extracted["city"]
            changed = True
        if extracted.get("genre"):
            rec["genre"] = extracted["genre"]
            changed = True
        if extracted.get("ticket_info") and not self._ticket_price_invented(rec.get("ticket_info"), extracted["ticket_info"]):
            rec["ticket_info"] = extracted["ticket_info"]
            changed = True
        if extracted.get("organizer") and (
            self._is_missing_text(rec.get("organizer")) or self._value_in_evidence(rec, extracted["organizer"])
        ):
            rec["organizer"] = extracted["organizer"]
            changed = True
        rec["venue"] = self._format_venue_with_city(rec.get("venue"), rec.get("city"))
        rec["ticket_info"] = self._compact_ticket_info(rec.get("ticket_info"))
        rec["genre"] = self._normalize_genre_tags(rec.get("genre"))
        catalog_normalize_event(rec)
        return changed

    def _apply_normalized_cache(self, rec, cached_row):
        if not cached_row:
            return False
        return self._apply_normalized_fields(rec, cached_row)

    def normalize_listing_records(self, records):
        """Shape every listing into SproutMe fields; LLM only the messy leftovers."""
        for rec in records:
            self._shape_record(rec)
        targets = [rec for rec in records if self._needs_normalize(rec)]
        if not targets:
            print("Listing fields already in SproutMe shape.")
            return records

        print(f"Normalizing {len(targets)} messy listings via {SCRAPE_OPENAI_MODEL}...")
        cached = self._lookup_cached_genres(targets) if self.supabase_client else {}
        remaining = []
        cache_hits = 0
        for rec in targets:
            cached_row = cached.get(self._genre_fingerprint(rec)) or {}
            if cached_row.get("event_name") or cached_row.get("venue"):
                if self._apply_normalized_cache(rec, cached_row) and not self._needs_normalize(rec):
                    cache_hits += 1
                    continue
            remaining.append(rec)
        print(f"Normalize cache hits: {cache_hits}. OpenAI normalize: {len(remaining)}.")

        labeled_now = []
        for start in range(0, len(remaining), NORMALIZE_BATCH_SIZE):
            batch = remaining[start:start + NORMALIZE_BATCH_SIZE]
            labels = {}
            try:
                labels = self._label_normalize_batch(batch)
            except Exception as e:
                print(f"OpenAI normalize batch failed, retrying once: {e}")
                time.sleep(2)
                try:
                    labels = self._label_normalize_batch(batch)
                except Exception as retry_error:
                    print(f"OpenAI normalize batch failed again: {retry_error}")
            for offset, rec in enumerate(batch):
                extracted = labels.get(offset) or {}
                if self._apply_normalized_fields(rec, extracted):
                    labeled_now.append(rec)
            print(f"Normalized {min(start + len(batch), len(remaining))}/{len(remaining)}.")
            if start + NORMALIZE_BATCH_SIZE < len(remaining):
                time.sleep(0.3)

        if self.supabase_client and labeled_now:
            self._save_cached_genres(labeled_now)
        for rec in records:
            self._shape_record(rec)
        return records

    def _public_event_row(self, rec):
        catalog_normalize_event(rec)
        row = {key: value for key, value in rec.items() if not str(key).startswith("_")}
        for field in ("event_url", "event_link_url"):
            if row.get(field):
                row[field] = clean_event_url(row[field])
        return row

    def fill_missing_event_fields(self, records):
        """Shape listings, extract headliners first, then genres/URLs/normalize."""
        print(f"Using scrape model {SCRAPE_OPENAI_MODEL}")
        for rec in records:
            self._shape_record(rec)
        # Headliner first: genre, heat, and score matching all depend on a clean act name.
        records = self.fill_missing_headliners(records)
        records = self.fill_missing_url_fields(records)
        records = self.fill_missing_genres(records)
        return self.normalize_listing_records(records)

    def _clean_headliner_text(self, value):
        text = " ".join(str(value or "").split()).strip(" -|/,")
        if not text:
            return ""
        if text.lower() in {"null", "none", "n/a", "tba", "tbd", "unknown"}:
            return ""
        return text[:80]

    def _serialize_artists(self, artists):
        cleaned = sanitize_headliners(artists, limit=3)
        return catalog_serialize_headliners(cleaned, limit=3)

    def _parse_artists_field(self, value):
        return catalog_parse_headliners(value, limit=3)

    def _heuristic_artists(self, event_name):
        try:
            from services.spotify_service import headliners_from_event_name
        except ImportError:
            from spotify_service import headliners_from_event_name
        parsed = headliners_from_event_name(event_name or "", limit=3)
        cleaned_parts = []
        for text in parsed:
            cleaned = re.sub(r"\b20\d{2}\b", " ", text)
            cleaned = re.sub(
                r"\b((north|south|latin)\s+america|europe|asia|australia|uk|usa|u\.s\.a\.?)\b",
                " ",
                cleaned,
                flags=re.I,
            )
            cleaned = re.sub(r"\b(world\s*)?tour\b", " ", cleaned, flags=re.I)
            cleaned = re.sub(r"\s+", " ", cleaned).strip(" -|/,")
            cleaned = self._clean_headliner_text(cleaned)
            if not cleaned or HEADLINER_JUNK_RE.search(cleaned):
                continue
            if cleaned not in cleaned_parts:
                cleaned_parts.append(cleaned)
        return cleaned_parts[:3]

    def _title_needs_llm_artists(self, event_name):
        name = event_name or ""
        if not name.strip():
            return False
        if MULTI_ACT_TITLE_RE.search(name):
            return True
        if HEADLINER_JUNK_RE.search(name):
            return True
        if len(name) > 36:
            return True
        return False

    def _needs_llm_artists(self, rec):
        if rec.get("_skip_enrich"):
            return False
        if self._parse_artists_field(rec.get("headliner")):
            return False
        name = rec.get("event_name") or ""
        return self._title_needs_llm_artists(name) or not name.strip()

    def _parse_headliner_labels(self, content, batch_size):
        text = (content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            parsed = json.loads(match.group(0)) if match else {}
        labels = parsed.get("headliners") if isinstance(parsed, dict) else parsed
        mapped = {}
        if not isinstance(labels, list):
            return mapped
        for item in labels:
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("i", item.get("index")))
            except (TypeError, ValueError):
                continue
            if index < 0 or index >= batch_size:
                continue
            artists = item.get("artists")
            if artists is None and item.get("headliner") is not None:
                artists = item.get("headliner")
            if isinstance(artists, str):
                artists = [part.strip() for part in artists.split(",") if part.strip()]
            if not isinstance(artists, list):
                artists = []
            mapped[index] = [
                self._clean_headliner_text(name)
                for name in artists
                if self._clean_headliner_text(name)
            ][:3]
        return mapped

    def _label_headliner_batch(self, batch):
        # Keep payload tiny — titles alone are enough for artist extraction.
        payload = [
            {"i": index, "event_name": rec.get("event_name") or ""}
            for index, rec in enumerate(batch)
        ]
        content = self._openai_chat([
            {"role": "system", "content": HEADLINER_PROMPT},
            {"role": "user", "content": json.dumps({"events": payload}, separators=(",", ":"))},
        ])
        return self._parse_headliner_labels(content, len(batch))

    def _apply_headliner_labels(self, batch, labels):
        labeled = 0
        for offset, rec in enumerate(batch):
            artists = labels.get(offset)
            if artists is None:
                artists = self._heuristic_artists(rec.get("event_name"))
            if artists:
                rec["headliner"] = self._serialize_artists(artists)
                labeled += 1
        return labeled

    def fill_missing_headliners(self, records, use_llm=True):
        """Attach artist lists sequentially: cache → heuristic → LLM leftovers.

        Heuristics run on every empty title first (including messy). LLM only
        fills what is still empty afterward when use_llm=True.
        """
        cached = {}
        if self.supabase_client:
            try:
                cached = self._lookup_cached_genres(records)
            except Exception as exc:
                print(f"Headliner cache lookup failed: {exc}")
                cached = {}

        heuristic_hits = 0
        cache_hits = 0
        for rec in records:
            existing = self._parse_artists_field(rec.get("headliner"))
            if existing:
                rec["headliner"] = self._serialize_artists(existing)
                continue

            cached_row = cached.get(self._genre_fingerprint(rec)) or {}
            cached_artists = self._parse_artists_field(cached_row.get("headliner"))
            if cached_artists:
                rec["headliner"] = self._serialize_artists(cached_artists)
                cache_hits += 1
                continue

            name = rec.get("event_name") or ""
            guessed = self._heuristic_artists(name)
            if guessed:
                rec["headliner"] = self._serialize_artists(guessed)
                heuristic_hits += 1

        filled_after_heuristic = sum(
            1 for rec in records if self._parse_artists_field(rec.get("headliner"))
        )
        print(
            f"Artist pass (cache/heuristic): cache={cache_hits}, heuristic={heuristic_hits}, "
            f"filled={filled_after_heuristic}/{len(records)}."
        )

        if not use_llm:
            newly_filled = [
                rec for rec in records
                if self._parse_artists_field(rec.get("headliner"))
            ]
            if self.supabase_client and newly_filled:
                self._save_cached_genres(newly_filled)
            return records

        targets = [
            rec for rec in records
            if not self._parse_artists_field(rec.get("headliner"))
            and not rec.get("_skip_enrich")
            and (
                self._title_needs_llm_artists(rec.get("event_name") or "")
                or not (rec.get("event_name") or "").strip()
            )
        ]
        if not targets:
            print("Artist LLM: nothing left to label.")
            newly_filled = [
                rec for rec in records
                if self._parse_artists_field(rec.get("headliner"))
            ]
            if self.supabase_client and newly_filled:
                self._save_cached_genres(newly_filled)
            return records

        print(
            f"Extracting artist lists for {len(targets)} remaining messy titles via {SCRAPE_OPENAI_MODEL}..."
        )
        batches = [
            targets[start:start + HEADLINER_BATCH_SIZE]
            for start in range(0, len(targets), HEADLINER_BATCH_SIZE)
        ]
        labeled = 0
        workers = min(HEADLINER_LLM_WORKERS, len(batches)) or 1

        def _run_batch(batch):
            try:
                return batch, self._label_headliner_batch(batch), None
            except Exception as exc:
                try:
                    time.sleep(1)
                    return batch, self._label_headliner_batch(batch), None
                except Exception as retry_error:
                    return batch, {}, f"{exc} / {retry_error}"

        completed = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_run_batch, batch) for batch in batches]
            for future in as_completed(futures):
                batch, labels, error = future.result()
                if error:
                    print(f"OpenAI headliner batch failed: {error}")
                labeled += self._apply_headliner_labels(batch, labels)
                completed += len(batch)
                print(f"Artist lists labeled {completed}/{len(targets)}.")

        filled = sum(1 for rec in records if self._parse_artists_field(rec.get("headliner")))
        print(f"Artist fill complete: {filled}/{len(records)} events have artists (AI {labeled}).")
        newly_filled = [
            rec for rec in records
            if self._parse_artists_field(rec.get("headliner"))
        ]
        if self.supabase_client and newly_filled:
            self._save_cached_genres(newly_filled)
        return records

    def backfill_missing_headliners(self, table_name="Events_table", use_llm=False, limit_llm=None):
        """Fill artist lists on existing rows without wiping. Heuristic first; LLM optional."""
        if not self.supabase_client:
            return False, "Supabase client not initialized."
        rows = []
        start = 0
        page = 1000
        while True:
            chunk = (
                self.supabase_client.table(table_name)
                .select("id,event_name,venue,city,organizer,headliner,raw_date,date,event_url,genre,ticket_info")
                .range(start, start + page - 1)
                .execute()
                .data
                or []
            )
            rows.extend(chunk)
            if len(chunk) < page:
                break
            start += page
        if not rows:
            return False, f"No rows in {table_name}."

        before = {
            row["id"]: self._serialize_artists(self._parse_artists_field(row.get("headliner")))
            for row in rows
            if row.get("id") is not None
        }
        before_filled = sum(1 for value in before.values() if value)

        self.fill_missing_headliners(rows, use_llm=False)
        after_heuristic = sum(1 for row in rows if self._parse_artists_field(row.get("headliner")))
        print(f"After heuristic: {after_heuristic}/{len(rows)} filled (was {before_filled}).")

        if use_llm:
            empty_messy = [
                row for row in rows
                if not self._parse_artists_field(row.get("headliner"))
                and self._title_needs_llm_artists(row.get("event_name") or "")
            ]
            if limit_llm is not None:
                empty_messy = empty_messy[: max(0, int(limit_llm))]
            skip_ids = set()
            if limit_llm is not None:
                target_ids = {row.get("id") for row in empty_messy}
                for row in rows:
                    if (
                        not self._parse_artists_field(row.get("headliner"))
                        and row.get("id") not in target_ids
                    ):
                        row["_skip_enrich"] = True
                        skip_ids.add(row.get("id"))
            print(f"LLM phase targeting {len(empty_messy)} empty messy titles...")
            self.fill_missing_headliners(rows, use_llm=True)
            for row in rows:
                if row.get("id") in skip_ids:
                    row.pop("_skip_enrich", None)

        after_filled = sum(1 for row in rows if self._parse_artists_field(row.get("headliner")))
        updated = 0
        for row in rows:
            row_id = row.get("id")
            if row_id is None:
                continue
            headliner = self._serialize_artists(self._parse_artists_field(row.get("headliner")))
            if not headliner or headliner == before.get(row_id):
                continue
            try:
                self.supabase_client.table(table_name).update(
                    {"headliner": headliner}
                ).eq("id", row_id).execute()
                updated += 1
            except Exception as exc:
                print(f"headliner update failed for {row_id}: {exc}")
        return True, (
            f"Artists: {before_filled} → {after_filled} filled; "
            f"{updated} rows updated in {table_name}."
        )

    def fill_missing_genres(self, records):
        """Fill blank/placeholder genres from cache, then OpenAI. Never persist none."""
        missing_indexes = [
            index for index, rec in enumerate(records)
            if self.genre_is_missing(rec.get("genre"))
        ]
        if not missing_indexes:
            print("All scraped events already have genre tags.")
            return records

        print(f"Filling genres for {len(missing_indexes)} events missing 19hz tags...")
        missing_records = [records[index] for index in missing_indexes]
        cached = self._lookup_cached_genres(missing_records) if self.supabase_client else {}

        unlabeled = []
        for rec in missing_records:
            cached_row = cached.get(self._genre_fingerprint(rec)) or {}
            if cached_row.get("genre"):
                rec["genre"] = cached_row["genre"]
            else:
                unlabeled.append(rec)

        print(f"Genre cache hits: {len(missing_records) - len(unlabeled)}. OpenAI labeling: {len(unlabeled)}.")
        labeled_now = []
        for start in range(0, len(unlabeled), GENRE_BATCH_SIZE):
            batch = unlabeled[start:start + GENRE_BATCH_SIZE]
            labels = {}
            try:
                labels = self._label_genre_batch(batch)
            except Exception as e:
                print(f"OpenAI genre batch failed, retrying once: {e}")
                time.sleep(2)
                try:
                    labels = self._label_genre_batch(batch)
                except Exception as retry_error:
                    print(f"OpenAI genre batch failed again: {retry_error}")
            for offset, rec in enumerate(batch):
                genre = labels.get(offset)
                if genre:
                    rec["genre"] = genre
                    labeled_now.append(rec)
                else:
                    rec["genre"] = FALLBACK_GENRE
            print(f"Labeled {min(start + len(batch), len(unlabeled))}/{len(unlabeled)} missing-genre events.")
            if start + GENRE_BATCH_SIZE < len(unlabeled):
                time.sleep(0.4)

        if self.supabase_client and labeled_now:
            self._save_cached_genres(labeled_now)

        fallbacks = 0
        for rec in records:
            if self.genre_is_missing(rec.get("genre")):
                rec["genre"] = FALLBACK_GENRE
                fallbacks += 1
        print(f"Genre fill complete. Fallback '{FALLBACK_GENRE}' used on {fallbacks} events.")
        return records

    def backfill_missing_genres(self, table_name="Events_table"):
        return self.backfill_missing_fields(table_name)

    def backfill_missing_fields(self, table_name="Events_table"):
        """Fill existing rows that still have empty genre/ticket/organizer/venue."""
        if not self.supabase_client:
            return False, "Supabase client not initialized."

        rows = []
        start = 0
        page = 1000
        while True:
            response = (
                self.supabase_client.table(table_name)
                .select("id,event_name,venue,city,organizer,event_url,event_link_url,ticket_info,genre,raw_date,date")
                .range(start, start + page - 1)
                .execute()
            )
            chunk = response.data or []
            rows.extend(chunk)
            if len(chunk) < page:
                break
            start += page

        missing = [row for row in rows if self._missing_fields(row)]
        if not missing:
            return True, f"No missing-field rows in {table_name}."

        print(f"Backfilling {len(missing)} of {len(rows)} {table_name} rows.")
        originals = {
            row["id"]: (row.get("genre"), row.get("ticket_info"), row.get("organizer"), row.get("venue"))
            for row in missing
        }
        self.fill_missing_event_fields(missing)

        updated = 0
        for rec in missing:
            current = (rec.get("genre"), rec.get("ticket_info"), rec.get("organizer"), rec.get("venue"))
            if current == originals.get(rec["id"]):
                continue
            payload = {
                "genre": rec.get("genre") or "",
                "ticket_info": rec.get("ticket_info") or "",
                "organizer": rec.get("organizer") or "",
                "venue": rec.get("venue") or "",
            }
            self.supabase_client.table(table_name).update(payload).eq("id", rec["id"]).execute()
            updated += 1
        return True, f"Updated missing fields on {updated} {table_name} rows."

    def clean_mashed_venues(self, table_name="Events_table"):
        """Peel glued 19hz tails so venue/city match Ticketmaster shape. Updates in place."""
        if not self.supabase_client:
            return False, "Supabase client not initialized."

        rows = []
        start = 0
        page = 1000
        while True:
            response = (
                self.supabase_client.table(table_name)
                .select("id,venue,city")
                .range(start, start + page - 1)
                .execute()
            )
            chunk = response.data or []
            rows.extend(chunk)
            if len(chunk) < page:
                break
            start += page

        changed = []
        for row in rows:
            venue = row.get("venue") or ""
            city = row.get("city") or ""
            if not venue:
                continue
            shaped = {"venue": venue, "city": city}
            self._shape_record(shaped)
            new_venue = shaped.get("venue") or venue
            new_city = shaped.get("city") or city
            if new_venue != venue or (new_city and new_city != city and not self._region_city(new_city)):
                changed.append({"id": row["id"], "venue": new_venue, "city": new_city or city})

        updated = 0
        def write_row(rec):
            payload = {"venue": rec["venue"]}
            if rec.get("city"):
                payload["city"] = rec["city"]
            self.supabase_client.table(table_name).update(payload).eq("id", rec["id"]).execute()
            return 1

        if changed:
            with ThreadPoolExecutor(max_workers=8) as pool:
                updated = sum(pool.map(write_row, changed))
        return True, f"Cleaned venue/city on {updated} of {len(rows)} {table_name} rows."

    def clean_mashed_cache_venues(self):
        """Peel glued 19hz tails out of event_genre_cache.venue."""
        if not self.supabase_client:
            return False, "Supabase client not initialized."
        rows = []
        start = 0
        page = 1000
        while True:
            response = (
                self.supabase_client.table("event_genre_cache")
                .select("fingerprint,venue")
                .range(start, start + page - 1)
                .execute()
            )
            chunk = response.data or []
            rows.extend(chunk)
            if len(chunk) < page:
                break
            start += page
        changed = []
        for row in rows:
            venue = row.get("venue") or ""
            if not venue or not self._venue_is_mashed(venue):
                continue
            cleaned = self._clean_cached_venue(venue)
            if cleaned and cleaned != venue:
                changed.append({"fingerprint": row["fingerprint"], "venue": cleaned})
        updated = 0

        def write_row(rec):
            self.supabase_client.table("event_genre_cache").update(
                {"venue": rec["venue"]}
            ).eq("fingerprint", rec["fingerprint"]).execute()
            return 1

        if changed:
            with ThreadPoolExecutor(max_workers=8) as pool:
                updated = sum(pool.map(write_row, changed))
        return True, f"Cleaned venue on {updated} of {len(rows)} event_genre_cache rows."
    
    def upload_to_supabase(self, table_name, fill_missing=True):
        """
        Upload event data to a Supabase table.
        
        Args:
            table_name (str): Name of the Supabase table.
                                      
        Returns:
            tuple: (success, response) where success is a boolean and
                response contains Supabase response data or error message.
        """
        if not self.supabase_client:
            return False, "Supabase client not initialized. Call init_supabase_client first."
        
        # Scrape events with no date filtering
        records = self.scrape_upcoming_events()
        extra = self._ticketmaster_events()
        if extra:
            from services.catalog_sources import merge_event_catalog
            records, added = merge_event_catalog(records, extra)
            print(f"Merged {len(added)} Ticketmaster events. Catalog size {len(records)}.")
        
        if not records:
            return False, "No events found."
        
        try:
            if fill_missing:
                records = self.fill_missing_event_fields(records)
            before = len(records)
            records = dedupe_event_records(records)
            if len(records) < before:
                print(f"Deduped catalog {before} → {len(records)} before insert.")
            try:
                self._refresh_venue_place_cache(records)
            except Exception as exc:
                print(f"Venue place cache failed; continuing upload: {exc}")
            try:
                self._refresh_artist_heat_cache(records)
            except Exception as exc:
                print(f"Artist heat cache failed; continuing upload: {exc}")

            inserted = 0
            for start in range(0, len(records), 200):
                chunk = [self._public_event_row(rec) for rec in records[start:start + 200]]
                response = self.supabase_client.table(table_name).insert(chunk).execute()
                if hasattr(response, 'error') and response.error:
                    return False, response.error
                inserted += len(chunk)
                print(f"Inserted {inserted}/{len(records)} events")

            return True, f"Successfully uploaded {inserted} events"
        except Exception as e:
            return False, str(e)

    def _refresh_artist_heat_cache(self, records, max_fetch=None, weekly=False):
        try:
            from services.artist_heat import MAX_FETCH_PER_RUN, refresh_artist_heat_cache
        except ImportError:
            from artist_heat import MAX_FETCH_PER_RUN, refresh_artist_heat_cache
        if max_fetch is None:
            max_fetch = MAX_FETCH_PER_RUN
        return refresh_artist_heat_cache(
            self.supabase_client,
            records,
            max_fetch=max_fetch,
            weekly=weekly,
        )

    def _refresh_venue_place_cache(self, records, max_fetch=None):
        try:
            from services.venue_places import MAX_FETCH_PER_RUN, refresh_venue_place_cache
        except ImportError:
            from venue_places import MAX_FETCH_PER_RUN, refresh_venue_place_cache
        if max_fetch is None:
            max_fetch = MAX_FETCH_PER_RUN
        return refresh_venue_place_cache(self.supabase_client, records, max_fetch=max_fetch)

    def cache_venues_from_table(self, table_name="Events_table"):
        if not self.supabase_client:
            return False, "Supabase client not initialized."
        records = []
        start = 0
        page = 1000
        while True:
            response = (
                self.supabase_client.table(table_name)
                .select("venue,city")
                .range(start, start + page - 1)
                .execute()
            )
            chunk = response.data or []
            records.extend(chunk)
            if len(chunk) < page:
                break
            start += page
        stats = self._refresh_venue_place_cache(records, max_fetch=None)
        return True, (
            f"Venue place cache from {len(records)} {table_name} rows: "
            f"{stats.get('venues', 0)} unique, {stats.get('hits', 0)} fresh, "
            f"{stats.get('fetched', 0)} fetched, {stats.get('errors', 0)} errors."
        )

    def _ticketmaster_events(self):
        try:
            from services.catalog_sources import fetch_ticketmaster_events
        except ImportError:
            from catalog_sources import fetch_ticketmaster_events
        return fetch_ticketmaster_events(os.environ.get("TICKETMASTER_API_KEY"))

    def merge_ticketmaster_into_table(self, table_name="Events_table"):
        if not self.supabase_client:
            return False, "Supabase client not initialized."
        extra = self._ticketmaster_events()
        if not extra:
            return False, "No Ticketmaster events returned. Set TICKETMASTER_API_KEY."
        existing = []
        start = 0
        page = 1000
        while True:
            response = (
                self.supabase_client.table(table_name)
                .select("event_name,venue,city,raw_date,date,event_url,event_link_url")
                .range(start, start + page - 1)
                .execute()
            )
            chunk = response.data or []
            existing.extend(chunk)
            if len(chunk) < page:
                break
            start += page
        from services.catalog_sources import merge_event_catalog
        _, added = merge_event_catalog(existing, extra)
        if not added:
            return True, f"Ticketmaster returned {len(extra)} events; all were duplicates of {len(existing)} existing rows."
        added = dedupe_event_records(added)
        inserted = 0
        for offset in range(0, len(added), 200):
            chunk = [self._public_event_row(rec) for rec in added[offset:offset + 200]]
            response = self.supabase_client.table(table_name).insert(chunk).execute()
            if hasattr(response, "error") and response.error:
                return False, response.error
            inserted += len(chunk)
        return True, f"Inserted {inserted} new Ticketmaster events into {table_name}."
    
    def scrape_and_upload_with_clear(self, table_name="Events_table", fill_missing=True):
        """
        Clear the table, then scrape and upload events.
        
        Args:
            table_name (str): Name of the Supabase table.
            
        Returns:
            tuple: (success, message) indicating result of operation
        """
        # First clear the table
        clear_result = self.clear_table(table_name)
        if not clear_result["success"]:
            return False, f"Failed to clear table: {clear_result['message']}"
            
        print(f"Successfully cleared {table_name}")
        
        # Then scrape and upload new data
        return self.upload_to_supabase(table_name, fill_missing=fill_missing)


def main():
    """Main function to run the event scraper and notification system."""
    extra_args = [arg for arg in sys.argv[1:] if arg not in (
        "--backfill-genres", "--backfill-missing", "--backfill-headliners",
        "--backfill-headliners-llm", "--skip-genre-fill", "--skip-fill",
        "--merge-ticketmaster", "--cache-venues", "--cache-artists",
        "--refresh-artist-heat", "--clean-venues",
    ) and not arg.startswith("--llm-limit=")]
    if extra_args:
        print(
            "Usage: scrape_and_send.py [--backfill-missing] [--backfill-genres] "
            "[--backfill-headliners] [--backfill-headliners-llm] [--llm-limit=N] "
            "[--skip-fill] [--merge-ticketmaster] [--cache-venues] [--cache-artists] "
            "[--refresh-artist-heat] [--clean-venues]"
        )
        return

    scraper = EventScraper(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY
    )
    if "--backfill-headliners" in sys.argv or "--backfill-headliners-llm" in sys.argv:
        use_llm = "--backfill-headliners-llm" in sys.argv
        limit_llm = None
        for arg in sys.argv:
            if arg.startswith("--llm-limit="):
                try:
                    limit_llm = int(arg.split("=", 1)[1])
                except ValueError:
                    limit_llm = None
        phase = "heuristic then LLM" if use_llm else "heuristic only"
        print(f"Backfilling headliners on Events_table ({phase})...")
        success, message = scraper.backfill_missing_headliners(
            table_name="Events_table",
            use_llm=use_llm,
            limit_llm=limit_llm,
        )
        print(message)
        print("Process completed." if success else "Process failed.")
        return
    if "--cache-artists" in sys.argv or "--refresh-artist-heat" in sys.argv:
        weekly = "--refresh-artist-heat" in sys.argv
        print("Caching Spotify artist heat from Events_table...")
        records = []
        start = 0
        page = 1000
        while True:
            chunk = scraper.supabase_client.table("Events_table").select("event_name").range(start, start + page - 1).execute().data or []
            records.extend(chunk)
            if len(chunk) < page:
                break
            start += page
        stats = scraper._refresh_artist_heat_cache(records, max_fetch=None, weekly=weekly)
        print(
            f"Artist heat: {stats.get('artists', 0)} unique, {stats.get('hits', 0)} fresh, "
            f"{stats.get('fetched', 0)} fetched, {stats.get('errors', 0)} errors."
        )
        print("Process completed." if not stats.get("errors") else "Process failed.")
        return
    if "--clean-venues" in sys.argv:
        print("Cleaning mashed 19hz venue strings in Events_table...")
        success, message = scraper.clean_mashed_venues(table_name="Events_table")
        print(message)
        print("Cleaning mashed 19hz venue strings in event_genre_cache...")
        cache_ok, cache_message = scraper.clean_mashed_cache_venues()
        print(cache_message)
        print("Process completed." if success and cache_ok else "Process failed.")
        return
    if "--cache-venues" in sys.argv:
        print("Caching Google Places data for venues already in Events_table...")
        success, message = scraper.cache_venues_from_table(table_name="Events_table")
        print(message)
        print("Process completed." if success else "Process failed.")
        return
    if "--merge-ticketmaster" in sys.argv:
        print("Merging Ticketmaster events into the existing catalog...")
        success, message = scraper.merge_ticketmaster_into_table(table_name="Events_table")
        print(message)
        print("Process completed." if success else "Process failed.")
        return
    if "--backfill-genres" in sys.argv or "--backfill-missing" in sys.argv:
        print("Backfilling missing event fields...")
        success, message = scraper.backfill_missing_fields(table_name="Events_table")
        print(message)
        print("Process completed." if success else "Process failed.")
        return

    print("Starting event management system...")
    print("Scraping and uploading ALL events...")
    fill_missing = "--skip-genre-fill" not in sys.argv and "--skip-fill" not in sys.argv
    if not fill_missing:
        print("Skipping OpenAI field fill for this run.")
    success, message = scraper.scrape_and_upload_with_clear(
        table_name="Events_table",
        fill_missing=fill_missing,
    )
    print(message)
    print("Process completed." if success else "Process failed.")


if __name__ == "__main__":
    main()