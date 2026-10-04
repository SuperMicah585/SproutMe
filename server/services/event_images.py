"""Attach flyer/poster images to catalog events during the daily scrape.

Strategy:
1. Ticketmaster rows already carry image URLs from the Discovery API — keep those.
2. For other events, fetch the event page and prefer og:image / JSON-LD / large <img>.
3. If several candidates remain, ask a cheap text model which URL is the flyer.
4. Optionally host non-Ticketmaster images in the public `event-images` bucket so
   daily wipe+insert can clear stale binaries with the catalog.
"""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

BUCKET = os.environ.get("EVENT_IMAGES_BUCKET") or "event-images"
HOST_NON_TM = (os.environ.get("EVENT_IMAGES_HOST") or "true").lower() not in ("0", "false", "no")
MAX_HOST_BYTES = int(os.environ.get("EVENT_IMAGES_MAX_BYTES") or 1_500_000)
MAX_FETCH_WORKERS = int(os.environ.get("EVENT_IMAGES_FETCH_WORKERS") or 12)
MAX_AI_PICKS = int(os.environ.get("EVENT_IMAGES_MAX_AI") or 400)
FETCH_TIMEOUT = int(os.environ.get("EVENT_IMAGES_FETCH_TIMEOUT") or 12)
SCRAPE_OPENAI_MODEL = os.environ.get("SCRAPE_OPENAI_MODEL") or "gpt-4.1-nano"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or ""

FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; SproutMeBot/1.0; +https://sproutme-please.com)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SKIP_HOST_BITS = (
    "facebook.com",
    "fb.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "youtube.com",
    "youtu.be",
    "linkedin.com",
    "google.com",
    "gstatic.com",
    "doubleclick",
    "analytics",
    "pixel",
    "sprite",
    "icon",
    "logo",
    "avatar",
    "1x1",
    "spacer",
)

PICK_PROMPT = """You pick the best event flyer/poster image URL for an EDM show listing.
Return JSON only: {"i": <index>} using the candidate index, or {"i": null} if none is a flyer.
Prefer: square/portrait flyer art, artist/event poster, Eventbrite/Dice/RA cover.
Avoid: logos, icons, maps, social badges, QR-only, tiny tracking pixels, venue exterior unless no flyer exists."""


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _provider(rec):
    source = rec.get("_source") if isinstance(rec.get("_source"), dict) else {}
    return (source.get("provider") or "").lower()


def best_ticketmaster_image(event):
    """Pick the best Ticketmaster Discovery image URL from a raw API event."""
    images = event.get("images") or []
    if not images:
        return ""
    scored = []
    for item in images:
        url = _clean(item.get("url"))
        if not url:
            continue
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        ratio = str(item.get("ratio") or "")
        # Distance from a ~1200px-wide card (good for widgets, not huge SOURCE files).
        target_w = 1200
        size_score = 500_000 - abs(width - target_w) * 250
        if width < 300 or height < 160:
            size_score -= 400_000
        if ratio == "16_9":
            size_score += 50_000
        elif ratio == "3_2":
            size_score += 20_000
        if item.get("fallback"):
            size_score -= 50_000
        name = url.upper()
        if "_SOURCE" in name:
            size_score -= 500_000
        if "RECOMENDATION" in name or "EVENT_DETAIL_PAGE" in name:
            size_score -= 200_000
        if "TABLET_LANDSCAPE_LARGE" in name or "RETINA_LANDSCAPE_16_9" in name:
            size_score += 80_000
        scored.append((size_score, url))
    if not scored:
        return ""
    scored.sort(reverse=True)
    return scored[0][1]


def _skip_url(url):
    lowered = (url or "").lower()
    if not lowered.startswith(("http://", "https://")):
        return True
    return any(bit in lowered for bit in SKIP_HOST_BITS)


def _abs_url(base_url, maybe_relative):
    raw = _clean(maybe_relative)
    if not raw or raw.startswith("data:"):
        return ""
    return urljoin(base_url or "", raw)


def extract_image_candidates(html, page_url=""):
    """Collect ranked flyer candidates from HTML without downloading binaries."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    ranked = []

    def add(url, score, source):
        full = _abs_url(page_url, url)
        if not full or _skip_url(full):
            return
        ranked.append({"url": full, "score": score, "source": source})

    for prop, score in (
        ("og:image", 1000),
        ("og:image:url", 990),
        ("og:image:secure_url", 980),
        ("twitter:image", 900),
        ("twitter:image:src", 890),
    ):
        tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            add(tag.get("content"), score, "og" if "og:" in prop else "twitter")

    for script in soup.find_all("script"):
        script_type = str(script.get("type") or "").lower()
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
            types = item.get("@type")
            type_names = types if isinstance(types, list) else [types]
            type_names = [str(name or "").lower() for name in type_names]
            images = item.get("image") or item.get("thumbnailUrl") or item.get("photo")
            image_list = images if isinstance(images, list) else [images] if images else []
            for image in image_list:
                if isinstance(image, dict):
                    url = image.get("url") or image.get("contentUrl") or image.get("@id")
                else:
                    url = image
                score = 850 if any("event" in name for name in type_names) else 700
                add(url, score, "jsonld")

    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        srcset = img.get("srcset") or ""
        if srcset and not src:
            first = srcset.split(",")[0].strip().split(" ")[0]
            src = first
        if not src:
            continue
        classes = " ".join(img.get("class") or []).lower()
        alt = (img.get("alt") or "").lower()
        width = int(img.get("width") or 0) if str(img.get("width") or "").isdigit() else 0
        height = int(img.get("height") or 0) if str(img.get("height") or "").isdigit() else 0
        score = 100 + min(width, 1200) + min(height, 1200)
        blob = f"{classes} {alt} {src}".lower()
        if any(token in blob for token in ("flyer", "poster", "event", "cover", "hero", "artwork")):
            score += 400
        if any(token in blob for token in ("logo", "icon", "avatar", "sprite", "badge")):
            score -= 500
        if width and height and width < 80 and height < 80:
            score -= 400
        add(src, score, "heuristic")

    # Deduplicate keeping highest score.
    best = {}
    for item in ranked:
        url = item["url"]
        prev = best.get(url)
        if not prev or item["score"] > prev["score"]:
            best[url] = item
    return sorted(best.values(), key=lambda item: item["score"], reverse=True)[:8]


def _openai_pick(candidates, event_meta):
    if not OPENAI_API_KEY or not candidates:
        return None
    payload = {
        "event": {
            "event_name": event_meta.get("event_name") or "",
            "venue": event_meta.get("venue") or "",
            "city": event_meta.get("city") or "",
        },
        "candidates": [
            {"i": index, "url": item["url"], "source": item.get("source")}
            for index, item in enumerate(candidates[:6])
        ],
    }
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model=SCRAPE_OPENAI_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": PICK_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.warning("event image AI pick failed: %s", exc)
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    try:
        index = parsed.get("i")
        if index is None:
            return None
        index = int(index)
    except (TypeError, ValueError):
        return None
    if 0 <= index < len(candidates):
        return candidates[index]
    return None


def _download_bytes(url):
    request = Request(url, headers={**FETCH_HEADERS, "Accept": "image/*,*/*;q=0.8"})
    with urlopen(request, timeout=FETCH_TIMEOUT) as response:
        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        data = response.read(MAX_HOST_BYTES + 1)
    if len(data) > MAX_HOST_BYTES:
        return None, ""
    if content_type and not content_type.startswith("image/"):
        # Some CDNs omit type; sniff extension instead.
        path = urlparse(url).path.lower()
        if not any(path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
            return None, ""
        content_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    if not content_type:
        content_type = "image/jpeg"
    if content_type in {"image/svg+xml", "image/svg", "text/html", "application/octet-stream"}:
        path = urlparse(url).path.lower()
        if content_type.startswith("image/svg") or path.endswith(".svg"):
            return None, ""
        if content_type == "text/html":
            return None, ""
        # octet-stream: only keep if path looks like a raster image
        if not any(path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif")):
            return None, ""
        content_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    if "svg" in content_type or content_type == "image/avif":
        return None, ""
    return data, content_type


def _storage_key(url, event_name=""):
    digest = hashlib.sha1(f"{url}|{event_name}".encode("utf-8")).hexdigest()[:20]
    path = urlparse(url).path.lower()
    ext = ".jpg"
    for candidate in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(candidate):
            ext = ".jpg" if candidate == ".jpeg" else candidate
            break
    return f"daily/{digest}{ext}"


def clear_event_image_bucket(supabase, bucket=BUCKET):
    """Delete all objects in the event-images bucket (daily catalog refresh)."""
    if not supabase:
        return {"deleted": 0}
    deleted = 0
    try:
        # Ensure bucket exists (idempotent).
        try:
            supabase.storage.get_bucket(bucket)
        except Exception:
            supabase.storage.create_bucket(
                bucket,
                options={
                    "public": True,
                    "file_size_limit": MAX_HOST_BYTES,
                    "allowed_mime_types": [
                        "image/jpeg",
                        "image/png",
                        "image/webp",
                        "image/gif",
                    ],
                },
            )
    except Exception as exc:
        logger.warning("event-images bucket ensure failed: %s", exc)

    prefixes = ["daily", ""]
    for prefix in prefixes:
        try:
            entries = supabase.storage.from_(bucket).list(prefix or "", {"limit": 1000})
        except Exception as exc:
            logger.warning("list %s/%s failed: %s", bucket, prefix, exc)
            continue
        paths = []
        for entry in entries or []:
            name = entry.get("name") if isinstance(entry, dict) else getattr(entry, "name", None)
            if not name:
                continue
            path = f"{prefix}/{name}" if prefix else name
            # Nested folders: list returned folders without id metadata sometimes.
            if entry.get("id") is None and entry.get("metadata") is None and prefix == "":
                # Treat as folder name; list inside.
                try:
                    nested = supabase.storage.from_(bucket).list(name, {"limit": 1000}) or []
                except Exception:
                    nested = []
                for child in nested:
                    child_name = child.get("name") if isinstance(child, dict) else None
                    if child_name:
                        paths.append(f"{name}/{child_name}")
                continue
            paths.append(path)
        # Chunk deletes
        for start in range(0, len(paths), 100):
            chunk = paths[start:start + 100]
            try:
                supabase.storage.from_(bucket).remove(chunk)
                deleted += len(chunk)
            except Exception as exc:
                logger.warning("delete chunk failed: %s", exc)
    return {"deleted": deleted}


def host_image(supabase, url, event_name="", bucket=BUCKET):
    """Download remote image and upload to public storage; return public URL."""
    if not supabase or not url:
        return ""
    try:
        data, content_type = _download_bytes(url)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        logger.info("image download failed %s: %s", url[:80], exc)
        return ""
    if not data:
        return ""
    key = _storage_key(url, event_name)
    try:
        supabase.storage.from_(bucket).upload(
            key,
            data,
            file_options={"content-type": content_type, "upsert": "true"},
        )
    except Exception as exc:
        # Upsert option naming differs across client versions.
        try:
            supabase.storage.from_(bucket).upload(
                key,
                data,
                {"content-type": content_type, "upsert": "true"},
            )
        except Exception as retry_exc:
            logger.warning("image upload failed %s: %s / %s", key, exc, retry_exc)
            return ""
    try:
        return supabase.storage.from_(bucket).get_public_url(key)
    except Exception:
        base = os.environ.get("SUPABASE_URL") or ""
        return f"{base.rstrip('/')}/storage/v1/object/public/{bucket}/{key}"


def _fetch_html(url):
    request = Request(url, headers=FETCH_HEADERS)
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT) as response:
            raw = response.read(400000)
            content_type = (response.headers.get("Content-Type") or "").lower()
    except Exception as exc:
        logger.info("event page fetch failed (%s): %s", (url or "")[:80], exc)
        return ""
    if content_type and "html" not in content_type and "xml" not in content_type:
        return ""
    return raw.decode("utf-8", errors="ignore")


def _choose_from_candidates(candidates, rec, allow_ai=True):
    if not candidates:
        return None
    top = candidates[0]
    # Strong structured signal — no AI needed.
    if top["score"] >= 850 or top.get("source") in {"og", "twitter", "jsonld"}:
        if len(candidates) == 1 or top["score"] >= candidates[1]["score"] + 80:
            return top
    if allow_ai:
        picked = _openai_pick(candidates, rec)
        if picked:
            picked = dict(picked)
            picked["source"] = "ai"
            return picked
    return top


def attach_event_images(supabase, records, *, host=HOST_NON_TM, max_ai=MAX_AI_PICKS):
    """Mutate records in place with image_url / image_source. Returns stats."""
    stats = {
        "total": len(records or []),
        "ticketmaster": 0,
        "scraped": 0,
        "hosted": 0,
        "ai": 0,
        "missing": 0,
    }
    if not records:
        return stats

    need_fetch = []
    for rec in records:
        if rec.get("image_url"):
            if _provider(rec) == "ticketmaster" or rec.get("image_source") == "ticketmaster":
                stats["ticketmaster"] += 1
            continue
        # Ticketmaster normally ships Discovery image_url at map time; if missing,
        # fall through and scrape the event page like other providers.
        urls = []
        for key in ("event_url", "event_link_url"):
            value = _clean(rec.get(key))
            if value and value.startswith("http") and not _skip_url(value):
                urls.append(value)
        if not urls:
            stats["missing"] += 1
            continue
        need_fetch.append((rec, urls[0]))

    page_html = {}
    unique_urls = list(dict.fromkeys(url for _, url in need_fetch))
    if unique_urls:
        print(f"Fetching {len(unique_urls)} event pages for flyer images...")
        with ThreadPoolExecutor(max_workers=MAX_FETCH_WORKERS) as pool:
            futures = {pool.submit(_fetch_html, url): url for url in unique_urls}
            done = 0
            for future in as_completed(futures):
                url = futures[future]
                page_html[url] = future.result() or ""
                done += 1
                if done % 50 == 0 or done == len(unique_urls):
                    print(f"Flyer pages {done}/{len(unique_urls)}")

    ai_used = 0
    for rec, page_url in need_fetch:
        html = page_html.get(page_url) or ""
        candidates = extract_image_candidates(html, page_url)
        allow_ai = ai_used < max_ai
        chosen = _choose_from_candidates(candidates, rec, allow_ai=allow_ai)
        if not chosen:
            stats["missing"] += 1
            continue
        if chosen.get("source") == "ai":
            ai_used += 1
            stats["ai"] += 1
        image_url = chosen["url"]
        image_source = chosen.get("source") or "heuristic"
        if host:
            hosted = host_image(supabase, image_url, event_name=rec.get("event_name") or "")
            if hosted:
                image_url = hosted
                image_source = f"hosted:{image_source}"
                stats["hosted"] += 1
        rec["image_url"] = image_url
        rec["image_source"] = image_source
        stats["scraped"] += 1

    still_missing = sum(1 for rec in records if not rec.get("image_url"))
    stats["missing"] = still_missing
    print(
        "Event images: "
        f"tm={stats['ticketmaster']} scraped={stats['scraped']} "
        f"hosted={stats['hosted']} ai={stats['ai']} missing={stats['missing']}"
    )
    return stats
