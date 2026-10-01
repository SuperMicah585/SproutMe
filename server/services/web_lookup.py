"""Short context lookups around a show. Not a second event catalog."""
import json
import logging
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

USER_AGENT = "SproutMeSMS/1.0 (show finder; https://sproutme-please.com)"
TIMEOUT_SEC = 4
MAX_SMS = 280


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _http_json(url, timeout=TIMEOUT_SEC):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    if not raw:
        return {}
    return json.loads(raw)


def _clip(text, limit=MAX_SMS):
    text = _clean(text)
    if len(text) <= limit:
        return text
    cut = text[: limit - 3].rsplit(" ", 1)[0]
    return (cut or text[: limit - 3]).rstrip(" ,;:-") + "..."


SKIP_TITLE_RE = re.compile(r"\b(museum|hotel|school|nrhp|boarding house|county)\b", re.I)
PLACE_RE = re.compile(
    r"\b(listed building|grade ii|museum|hotel|school|architect|kingsway|strand in london)\b",
    re.I,
)
MUSIC_HINT_RE = re.compile(r"\b(music|dj|genre|musician|band|song|producer|house music)\b", re.I)


def _wiki_summary(title):
    slug = quote(title.replace(" ", "_"), safe="_()!,*'")
    return _http_json(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}")


def _extract_from_summary(summary):
    extract = _clean(summary.get("extract") or summary.get("description"))
    if not extract:
        return ""
    kind = (summary.get("type") or "").lower()
    jammed = (
        extract.lower().startswith("may refer to")
        or "may refer to:" in extract.lower()
        or kind == "disambiguation"
    )
    if jammed:
        match = re.search(r".{0,40}\b(?:music|genre|dj|musician)\b.{0,90}", extract, re.I)
        snippet = _clean(match.group(0) if match else "")
        snippet = re.split(r"\s+(?=[A-Z][a-z]+(?:-[A-Z][a-z]+)?\s+[A-Z])", snippet)[0]
        snippet = re.sub(r"^(?:.+ may refer to:?)", "", snippet, flags=re.I).strip(" :")
        if snippet and MUSIC_HINT_RE.search(snippet) and not SKIP_TITLE_RE.search(snippet) and not PLACE_RE.search(snippet):
            return snippet
        return ""
    if PLACE_RE.search(extract[:160]) and not MUSIC_HINT_RE.search(extract[:160]):
        return ""
    if SKIP_TITLE_RE.search(extract[:120]):
        return ""
    return extract


def _wikipedia(query):
    needle = _clean(query)
    if len(needle) < 2:
        return None
    search_url = "https://en.wikipedia.org/w/api.php?" + urlencode({
        "action": "opensearch",
        "search": needle,
        "limit": 8,
        "namespace": 0,
        "format": "json",
    })
    data = _http_json(search_url)
    titles = list(data[1] if isinstance(data, list) and len(data) > 1 else [])
    extra = f"{needle} music"
    extra_url = "https://en.wikipedia.org/w/api.php?" + urlencode({
        "action": "opensearch",
        "search": extra,
        "limit": 3,
        "namespace": 0,
        "format": "json",
    })
    try:
        extra_data = _http_json(extra_url)
        titles.extend(extra_data[1] if isinstance(extra_data, list) and len(extra_data) > 1 else [])
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
        pass
    seen = set()
    ranked = []
    lowered = needle.lower()
    for title in titles or [needle]:
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        if SKIP_TITLE_RE.search(title):
            continue
        score = 0
        if key == lowered or key.startswith(lowered):
            score += 3
        if MUSIC_HINT_RE.search(title):
            score += 5
        ranked.append((score, title))
    ranked.sort(reverse=True)
    for _, title in ranked[:4] or [(0, needle)]:
        try:
            summary = _wiki_summary(title)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError):
            continue
        extract = _extract_from_summary(summary)
        if not extract:
            continue
        page_url = ((summary.get("content_urls") or {}).get("desktop") or {}).get("page") or ""
        return {
            "source": "wikipedia",
            "title": summary.get("title") or title,
            "summary": extract,
            "url": page_url.replace("https://", ""),
        }
    return None


def _musicbrainz(query):
    needle = _clean(query)
    if len(needle) < 2:
        return None
    url = "https://musicbrainz.org/ws/2/artist/?" + urlencode({
        "query": f'artist:"{needle}"',
        "fmt": "json",
        "limit": 1,
    })
    data = _http_json(url)
    artists = data.get("artists") or []
    if not artists:
        url = "https://musicbrainz.org/ws/2/artist/?" + urlencode({
            "query": needle,
            "fmt": "json",
            "limit": 1,
        })
        data = _http_json(url)
        artists = data.get("artists") or []
    artist = artists[0] if artists else None
    if not artist:
        return None
    name = _clean(artist.get("name"))
    disambig = _clean(artist.get("disambiguation"))
    tags = [_clean(item.get("name")) for item in (artist.get("tags") or []) if _clean(item.get("name"))]
    tags = tags[:4]
    bits = [name]
    if disambig:
        bits.append(disambig)
    if tags:
        bits.append("tags: " + ", ".join(tags))
    summary = " — ".join(part for part in bits if part)
    mbid = artist.get("id") or ""
    return {
        "source": "musicbrainz",
        "title": name,
        "summary": summary,
        "url": f"musicbrainz.org/artist/{mbid}" if mbid else "",
        "tags": tags,
    }


def lookup_context(query):
    query = _clean(query)
    if len(query) < 2:
        return {"error": "missing_query", "sms": ""}
    hits = []
    for getter in (_wikipedia, _musicbrainz):
        try:
            hit = getter(query)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            logger.info("lookup %s failed for %s: %s", getter.__name__, query, exc)
            continue
        if hit and hit.get("summary"):
            hits.append(hit)
            break
    if not hits:
        return {
            "query": query,
            "found": False,
            "sms": "",
            "summary": "",
        }
    hit = hits[0]
    sms = _clip(hit["summary"])
    return {
        "query": query,
        "found": True,
        "source": hit.get("source"),
        "title": hit.get("title"),
        "summary": hit.get("summary"),
        "url": hit.get("url") or "",
        "sms": sms,
    }


def research_local(city, topic="", origin=""):
    """
    Ground place-specific / ambiguous planning constraints for a city.

    Not a distance matcher and not a show catalog. Deep SMS uses this when
    a constraint depends on local knowledge (transit, neighborhoods, districts,
    "downtown", walkable-from-X, etc.) instead of hardcoded per-city databases.
    """
    city = _clean(city)
    topic = _clean(topic) or "public transit nightlife areas"
    origin = _clean(origin)
    if len(city) < 2:
        return {"error": "missing_city", "found": False, "sms": "", "hits": []}

    topic_l = topic.lower()
    is_transit = bool(re.search(
        r"\b(transit|transport|rail|metro|bus|no\s*car|car[- ]?free|walkable|trimet|link|max|bart)\b",
        topic_l,
    ))
    is_area = bool(re.search(
        r"\b(neighborhood|district|downtown|southwest|southeast|northeast|northwest|"
        r"capitol hill|ballard|queen anne|lido|loDo|origin|staying)\b",
        topic_l,
        re.I,
    )) or bool(origin)

    queries = []
    if is_transit:
        queries.extend([
            f"Public transportation in {city}",
            f"{city} public transportation",
            f"{city} TriMet" if "portland" in city.lower() else f"{city} transit",
            f"{city} light rail",
            f"{city} metro",
        ])
    if is_area or origin:
        place = origin or topic
        queries.extend([
            f"{place}, {city}",
            f"{place} {city}",
            f"{city} {place}",
        ])
    if not is_transit:
        queries.extend([
            f"{city} {topic}",
            f"{topic} {city}",
            f"Public transportation in {city}",
        ])

    # De-dupe while preserving order
    seen_q = set()
    ordered = []
    for q in queries:
        key = q.lower()
        if key in seen_q or len(_clean(q)) < 4:
            continue
        seen_q.add(key)
        ordered.append(q)

    def _relevant(title, summary):
        blob = f"{title} {summary}".lower()
        # Reject obvious junk
        if re.search(
            r"\b(tunnel|abandoned|nrhp|national register|song|album|film|novel|"
            r"hotel|school|museum|cemetery|bridge listed)\b",
            blob,
        ) and not re.search(r"\b(transit|transport|metro|neighborhood|district)\b", blob[:120]):
            return False
        if is_transit:
            return bool(re.search(
                r"\b(transit|transport|metro|subway|rail|tram|streetcar|bus|ferry|"
                r"max|link|bart|mta|cta|trimet|sound transit|rtd|marta|wmata)\b",
                blob,
            ))
        if is_area:
            return bool(re.search(
                r"\b(neighborhood|district|downtown|quarter|area|suburb|community|"
                r"portland|seattle|denver|city)\b",
                blob,
            ))
        # Generic: require city name or topic token overlap
        city_token = city.lower().split(",")[0].split()[0]
        return city_token in blob or any(
            len(tok) > 3 and tok in blob for tok in re.findall(r"[a-z]+", topic_l)
        )

    hits = []
    seen_titles = set()
    for query in ordered:
        try:
            hit = _wikipedia(query)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            logger.info("local research wiki failed for %s: %s", query, exc)
            continue
        if not hit or not hit.get("summary"):
            continue
        title = _clean(hit.get("title") or query)
        summary = _clean(hit.get("summary"))
        if not _relevant(title, summary):
            continue
        key = title.lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        hits.append({
            "title": title,
            "summary": summary,
            "url": hit.get("url") or "",
            "source": hit.get("source") or "wikipedia",
            "query": query,
        })
        if len(hits) >= 3:
            break

    if not hits:
        return {
            "city": city,
            "topic": topic,
            "origin": origin or None,
            "found": False,
            "hits": [],
            "sms": f"No solid local overview for '{topic}' in {city}. Be cautious; do not invent local facts.",
            "guidance": (
                "Research missed. Do not invent stops, boundaries, or local slang. "
                "Prefer central/well-known venues and say uncertainty plainly."
            ),
        }

    lines = [f"Local research — {city} / {topic}" + (f" (from {origin})" if origin else "") + ":"]
    for item in hits:
        lines.append(f"- {item['title']}: {_clip(item['summary'], 220)}")
    guidance = (
        "Use this to interpret the texter's local constraint for THIS city. "
        "Catalog tools still supply shows — this only grounds meaning. "
        "Never invent place-specific facts beyond what research (or venue lookup) supports. "
        "There is no per-city distance/matcher database to lean on."
    )
    if origin:
        guidance += f" Starting point: {origin}."

    return {
        "city": city,
        "topic": topic,
        "origin": origin or None,
        "found": True,
        "hits": hits,
        "guidance": guidance,
        "sms": _clip(" | ".join(lines), 400),
        "summary": "\n".join(lines),
    }


def research_city_transit(city, origin=""):
    """Backward-compatible wrapper — prefer research_local."""
    return research_local(city, topic="public transportation transit rail bus", origin=origin)
