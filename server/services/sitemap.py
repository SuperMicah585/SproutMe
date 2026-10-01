"""Dynamic SEO sitemaps for the SproutMe marketing site."""

from __future__ import annotations

import re
from datetime import date
from xml.sax.saxutils import escape

from flask import Response

SITE_URL = "https://sproutme-please.com"
API_SITEMAP_BASE = "https://sproutme-api-production.up.railway.app"
MAX_EVENT_URLS = 5000
MIN_COMBO_COUNT = 5


def slugify(value: str) -> str:
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80]


def event_slug(event: dict) -> str:
    bits = [
        event.get("event_name") or "",
        event.get("venue") or "",
        event.get("city") or "",
    ]
    return slugify(" ".join(bit for bit in bits if bit)) or "show"


def event_path(event: dict) -> str | None:
    event_id = event.get("id")
    if event_id is None or event_id == "":
        return None
    return f"/event/{event_id}/{event_slug(event)}"


def _today_iso() -> str:
    return date.today().isoformat()


def _xml_response(body: str) -> Response:
    return Response(
        body,
        mimetype="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _url_entry(loc_path: str, lastmod: str | None = None, changefreq: str = "daily", priority: str = "0.7") -> str:
    loc = loc_path if loc_path.startswith("http") else f"{SITE_URL}{loc_path}"
    parts = [f"  <url>\n    <loc>{escape(loc)}</loc>"]
    if lastmod:
        parts.append(f"    <lastmod>{escape(lastmod)}</lastmod>")
    parts.append(f"    <changefreq>{escape(changefreq)}</changefreq>")
    parts.append(f"    <priority>{escape(priority)}</priority>")
    parts.append("  </url>")
    return "\n".join(parts)


def render_urlset(entries: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )


def render_sitemap_index(locs: list[str]) -> str:
    today = _today_iso()
    items = []
    for loc in locs:
        items.append(
            "  <sitemap>\n"
            f"    <loc>{escape(loc)}</loc>\n"
            f"    <lastmod>{escape(today)}</lastmod>\n"
            "  </sitemap>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(items)
        + "\n</sitemapindex>\n"
    )


def build_static_entries() -> list[str]:
    today = _today_iso()
    return [
        _url_entry("/", today, "daily", "1.0"),
        _url_entry("/events", today, "daily", "1.0"),
    ]


def build_city_entries(facets: dict) -> list[str]:
    today = _today_iso()
    entries = []
    seen = set()
    for row in facets.get("cities") or []:
        name = (row.get("name") or "").strip()
        slug = slugify(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        entries.append(_url_entry(f"/events/in/{slug}", today, "daily", "0.8"))
    return entries


def build_genre_entries(facets: dict) -> list[str]:
    today = _today_iso()
    entries = []
    seen = set()
    for row in facets.get("genres") or []:
        name = (row.get("name") or "").strip()
        if not name or name.lower() == "none":
            continue
        slug = slugify(name)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        entries.append(_url_entry(f"/events/genre/{slug}", today, "daily", "0.7"))
    return entries


def build_city_genre_entries(events: list, extract_city, min_count: int = MIN_COMBO_COUNT) -> list[str]:
    today = _today_iso()
    counts: dict[tuple[str, str], int] = {}
    labels: dict[tuple[str, str], tuple[str, str]] = {}
    for event in events:
        city = (event.get("city") or "").strip() or (extract_city(event.get("venue") or "") or "").strip()
        raw_genre = (event.get("genre") or "").strip()
        if not city or not raw_genre:
            continue
        for genre in [part.strip() for part in raw_genre.split(",") if part.strip()]:
            if genre.lower() == "none":
                continue
            city_slug = slugify(city)
            genre_slug = slugify(genre)
            if not city_slug or not genre_slug:
                continue
            key = (city_slug, genre_slug)
            counts[key] = counts.get(key, 0) + 1
            labels[key] = (city, genre)

    entries = []
    for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0][0], item[0][1])):
        if count < min_count:
            continue
        city_slug, genre_slug = key
        entries.append(
            _url_entry(f"/events/in/{city_slug}/genre/{genre_slug}", today, "daily", "0.6")
        )
    return entries


def build_event_entries(events: list, parse_event_day, max_urls: int = MAX_EVENT_URLS) -> list[str]:
    today = date.today()
    ranked = []
    for event in events:
        path = event_path(event)
        if not path:
            continue
        day = parse_event_day(event.get("raw_date") or event.get("date"))
        if day and day < today:
            continue
        ranked.append((day or date(9999, 12, 31), path, event))
    ranked.sort(key=lambda item: (item[0], str(item[2].get("event_name") or "")))

    entries = []
    for day, path, _event in ranked[:max_urls]:
        lastmod = day.isoformat() if isinstance(day, date) and day.year < 9999 else _today_iso()
        entries.append(_url_entry(path, lastmod, "weekly", "0.5"))
    return entries


def register_sitemaps(app, *, load_catalog, build_facets, extract_city, parse_event_day):
    def _catalog_and_facets():
        catalog = load_catalog() or []
        facets = build_facets(catalog)
        return catalog, facets

    @app.route("/sitemap.xml", methods=["GET"])
    def sitemap_index():
        locs = [
            f"{API_SITEMAP_BASE}/sitemaps/static.xml",
            f"{API_SITEMAP_BASE}/sitemaps/cities.xml",
            f"{API_SITEMAP_BASE}/sitemaps/genres.xml",
            f"{API_SITEMAP_BASE}/sitemaps/city-genres.xml",
            f"{API_SITEMAP_BASE}/sitemaps/events.xml",
        ]
        return _xml_response(render_sitemap_index(locs))

    @app.route("/sitemaps/static.xml", methods=["GET"])
    def sitemap_static():
        return _xml_response(render_urlset(build_static_entries()))

    @app.route("/sitemaps/cities.xml", methods=["GET"])
    def sitemap_cities():
        _catalog, facets = _catalog_and_facets()
        return _xml_response(render_urlset(build_city_entries(facets)))

    @app.route("/sitemaps/genres.xml", methods=["GET"])
    def sitemap_genres():
        _catalog, facets = _catalog_and_facets()
        return _xml_response(render_urlset(build_genre_entries(facets)))

    @app.route("/sitemaps/city-genres.xml", methods=["GET"])
    def sitemap_city_genres():
        catalog, _facets = _catalog_and_facets()
        return _xml_response(
            render_urlset(build_city_genre_entries(catalog, extract_city, MIN_COMBO_COUNT))
        )

    @app.route("/sitemaps/events.xml", methods=["GET"])
    def sitemap_events():
        catalog, _facets = _catalog_and_facets()
        return _xml_response(
            render_urlset(build_event_entries(catalog, parse_event_day, MAX_EVENT_URLS))
        )
