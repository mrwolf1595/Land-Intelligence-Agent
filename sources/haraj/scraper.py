"""
Haraj.com.sa real estate scraper — SSR-based (v2).

Haraj migrated from a paginated GraphQL API to React Router 7 with server-side
rendering.  All listing data is now embedded in the page HTML as a turbo-stream
payload inside a ``streamController.enqueue(...)`` script tag.

Strategy
--------
* Fetch ``https://haraj.com.sa/tags/اراضي-للبيع-في-{city}/`` for each target city.
* Also fetch the national ``اراضي-للبيع`` tag as a catch-all.
* Parse the turbo-stream flat-array format to reconstruct the posts list.
* If the SSR format changes, fall back to BeautifulSoup HTML card parsing.
* Normalise to the project schema (listing_id, city, area_sqm, price_sar, …).

Yield   : ~95–130 unique land listings across Saudi Arabia per run.
Delay   : 1.0 s between requests (polite crawling).
"""

import re
import time
import json
from datetime import datetime
from typing import Optional
from urllib.parse import quote

import httpx

from sources.base import BaseSource
from config import TARGET_CITIES, PRICE_MIN, PRICE_MAX
from core.logger import get_logger
from core.database import listing_exists

logger = get_logger("haraj")

_BASE      = "https://haraj.com.sa"
_API_BASE  = "https://haraj.com.sa/api"
_API_TAG   = f"{_API_BASE}/getTag"        # GET /api/getTag?tag=X&city=Y&page=N
_API_SRCH  = f"{_API_BASE}/searchPosts"   # GET /api/searchPosts?query=أرض&city=X
_LAND_TAG  = "اراضي-للبيع"          # national tag (catch-all)
_CITY_TAG  = "اراضي-للبيع-في-{city}" # city-specific tag template

# Known city slug corrections (display name → tag slug used by Haraj)
_CITY_SLUG = {
    "مكة":    "مكة-المكرمة",
    "جدة":    "جده",
    "القصيم": "بريدة",
}

# City name normalisations: Haraj may store alternate spellings in post data
_CITY_NORM = {
    "جده":  "جدة",
    "مكه":  "مكة",
    "مكة-المكرمة": "مكة",
    "المدينة-المنورة": "المدينة",
    "بريدة": "القصيم",
}

_HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.5",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# ── turbo-stream parser ───────────────────────────────────────────────────────

def _extract_turbo_array(html: str) -> Optional[list]:
    """
    Extract the flat turbo-stream array from the React Router 7 SSR payload.

    The data lives inside:
        <script>
            window.__reactRouterContext.streamController.enqueue("[ … JSON … ]");
        </script>

    IMPORTANT: the inner value is a JS string literal, so any embedded quote
    chars are escaped as \\".  We must use a pattern that handles escape
    sequences correctly (``[^"\\\\]|\\\\.`` idiom) instead of naive ``.*?``.
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    for s in scripts:
        if "streamController" not in s or "enqueue" not in s:
            continue
        # Handle escaped characters inside the JS string literal properly
        m = re.search(
            r'streamController\.enqueue\((\"(?:[^\"\\]|\\.)*\")\)',
            s,
            re.DOTALL,
        )
        if not m:
            continue
        try:
            inner = json.loads(m.group(1))  # unescape JS string → JSON string
            return json.loads(inner)         # parse flat array
        except Exception as exc:
            logger.debug(f"[haraj] turbo-stream parse error: {exc}")
            continue
    return None


def _resolve(idx: int, arr: list, depth: int = 0):
    """
    Dereference a turbo-stream index into a Python value.

    The format uses ``{"_<key_index>": <value_index>}`` objects where both
    key and value are positions in the flat *arr* list.  Negative integers
    encode ``undefined``/``null``.
    """
    if depth > 25:
        return None
    if not isinstance(idx, int) or idx < 0 or idx >= len(arr):
        return None
    v = arr[idx]
    if isinstance(v, dict):
        result = {}
        for k, val_ref in v.items():
            if k.startswith("_"):
                key_idx = int(k[1:])
                real_key = arr[key_idx] if key_idx < len(arr) and isinstance(arr[key_idx], str) else k
                real_val = _resolve(val_ref, arr, depth + 1) if isinstance(val_ref, int) else val_ref
                result[real_key] = real_val
        return result
    if isinstance(v, list):
        return [_resolve(i, arr, depth + 1) if isinstance(i, int) else i for i in v]
    return v


def _extract_posts(arr: list) -> list[dict]:
    """Walk the turbo-stream array and return all decoded post objects."""
    # Locate the "items" key index in the array
    items_key_idx = next((i for i, v in enumerate(arr) if v == "items"), None)
    if items_key_idx is None:
        return []

    posts: list[dict] = []
    seen_ids: set[int] = set()

    for item in arr:
        if not isinstance(item, dict) or f"_{items_key_idx}" not in item:
            continue
        items_list_ref = item[f"_{items_key_idx}"]
        if not isinstance(items_list_ref, int) or items_list_ref < 0:
            continue
        items_list = arr[items_list_ref] if items_list_ref < len(arr) else None
        if not isinstance(items_list, list):
            continue

        for post_ref in items_list:
            if not isinstance(post_ref, int) or post_ref < 0 or post_ref >= len(arr):
                continue
            post = _resolve(post_ref, arr)
            if not isinstance(post, dict):
                continue
            pid = post.get("id")
            if not isinstance(pid, int) or pid <= 100_000 or pid in seen_ids:
                continue
            seen_ids.add(pid)
            posts.append(post)

    return posts


# ── BeautifulSoup HTML fallback ───────────────────────────────────────────────

def _extract_posts_html(html: str) -> list[dict]:
    """
    Fallback parser: scan the rendered HTML for post cards when the
    turbo-stream payload isn't available (Haraj layout update, etc.).
    Returns minimal dicts with keys: id, title, city, price, bodyTEXT, URL.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    posts = []
    seen_ids: set[str] = set()

    # Haraj post cards carry a data-post-id or are <article> / <div> with href
    for card in soup.find_all(["article", "div"], attrs={"data-post-id": True}):
        pid_str = card.get("data-post-id", "")
        if not pid_str or pid_str in seen_ids:
            continue
        seen_ids.add(pid_str)

        title_el = card.find(["h2", "h3", "a"])
        title = title_el.get_text(strip=True) if title_el else ""

        body_el = card.find("p")
        body = body_el.get_text(strip=True) if body_el else ""

        link_el = card.find("a", href=True)
        url = link_el["href"] if link_el else ""
        if url and not url.startswith("http"):
            url = f"{_BASE}/{url.lstrip('/')}"

        price_el = card.find(string=re.compile(r"\d[\d,\.]+"))
        price = 0.0
        if price_el:
            nums = re.findall(r"[\d,]+", str(price_el))
            if nums:
                try:
                    price = float(nums[0].replace(",", ""))
                except ValueError:
                    pass

        try:
            pid = int(pid_str)
        except ValueError:
            continue

        posts.append({
            "id": pid,
            "title": title,
            "bodyTEXT": body,
            "price": price,
            "URL": url,
            "city": "",
        })

    logger.info(f"[haraj] HTML fallback: {len(posts)} post cards found")
    return posts


# ── helpers ───────────────────────────────────────────────────────────────────

def _phone_from_text(text: str) -> Optional[str]:
    m = re.search(r"(?:05\d{8}|\+9665\d{8}|009665\d{8})", text or "")
    return m.group(0) if m else None


def _area_from_text(text: str) -> float:
    m = re.search(r"(\d[\d,.]+)\s*م(?:²|2|²)?", text or "")
    if m:
        return float(m.group(1).replace(",", ""))
    return 0.0


def _price_from_text(text: str, area_sqm: float = 0.0) -> float:
    """Extract price in SAR from Arabic free-text body.

    Patterns tried (first match wins, except pattern 3 uses largest):
      1. Explicit label:   السعر: 960,000 ريال
      2. Million shorthand: 1.5 مليون
      3. Riyal / SAR suffix: 960,000 ريال  (largest number wins)
      4. Per-m² unit price: سعر الوحدة 7  → 7 × area_sqm
    """
    if not text:
        return 0.0

    # Pattern 1: labelled price  السعر: 960,000  or  سعر الأرض: 960,000
    m = re.search(r"(?:السعر|سعر[^:]*?)\s*[:：]\s*([\d,\.]+)", text)
    if m:
        val = float(m.group(1).replace(",", ""))
        if val > 100:          # sanity: must be > 100 SAR
            return val

    # Pattern 2: مليون (million)
    m = re.search(r"([\d\.]+)\s*مليون", text)
    if m:
        val = float(m.group(1).replace(",", "")) * 1_000_000
        if val >= 100_000:
            return val

    # Pattern 3: number followed by ريال or SAR — take the largest
    matches_rial = re.findall(r"([\d,]+)\s*(?:ريال|SAR)", text)
    if matches_rial:
        vals = [float(x.replace(",", "")) for x in matches_rial]
        best = max(vals)
        if best > 100:
            return best

    # Pattern 4: per-m² unit price × area
    m = re.search(r"سعر الوحدة\s*[:：]?\s*([\d,\.]+)", text)
    if m and area_sqm > 0:
        per_sqm = float(m.group(1).replace(",", ""))
        if per_sqm > 0:
            return per_sqm * area_sqm

    return 0.0


def _city_slug(city: str) -> str:
    return _CITY_SLUG.get(city, city)


def _normalise_city(city: str) -> str:
    """Normalise known Haraj city spellings to our TARGET_CITIES spelling."""
    c = (city or "").strip()
    return _CITY_NORM.get(c, c)


def _city_in_targets(city: str) -> bool:
    c = _normalise_city((city or "").strip())
    if not c:
        return False
    return any(t in c or c in t for t in TARGET_CITIES)


# ── scraper ───────────────────────────────────────────────────────────────────

class Scraper(BaseSource):
    name = "haraj"

    def __init__(self):
        self._client = httpx.Client(
            headers=_HEADERS,
            timeout=30,
            follow_redirects=True,
        )

    # ── Direct JSON API (strategy 0) ─────────────────────────────────────────

    def _fetch_api(self, tag: str, city: str = "") -> Optional[list[dict]]:
        """Try Haraj's internal JSON API before falling back to HTML parsing."""
        all_posts = []
        for page in range(1, 6):
            params = {"tag": tag, "page": page}
            if city:
                params["city"] = city
            try:
                resp = self._client.get(_API_TAG, params=params)
                if resp.status_code != 200:
                    break
                data = resp.json()
            except Exception:
                return None

            posts = (
                data.get("data", {}).get("posts") or
                data.get("posts") or
                data.get("items") or
                (data if isinstance(data, list) else [])
            )
            if not posts:
                break
            all_posts.extend(p for p in posts if isinstance(p, dict))
            if len(posts) < 10:
                break
            time.sleep(0.5)

        if not all_posts:
            # Try search endpoint as secondary attempt
            try:
                params = {"query": "أرض للبيع", "page": 1}
                if city:
                    params["city"] = city
                resp = self._client.get(_API_SRCH, params=params)
                if resp.status_code == 200:
                    d = resp.json()
                    all_posts = d.get("data", {}).get("posts") or d.get("posts") or []
            except Exception:
                pass

        return all_posts if all_posts else None

    # ── BaseSource interface ──────────────────────────────────────────────────

    def fetch(self) -> list[dict]:
        all_items: list[dict] = []
        seen_ids: set[int] = set()
        _EARLY_STOP = 10

        # Build list of tag URLs to scrape:
        # 1. National land tag (catch-all)
        # 2. City-specific tags for each target city
        tag_urls: list[tuple[str, str]] = [
            ("national", f"{_BASE}/tags/{quote(_LAND_TAG)}/"),
        ]
        for city in TARGET_CITIES:
            slug = _city_slug(city)
            tag = _CITY_TAG.format(city=slug)
            tag_urls.append((city, f"{_BASE}/tags/{quote(tag)}/"))

        logger.info(f"Haraj: scraping {len(tag_urls)} tag pages")

        for label, url in tag_urls:
            try:
                # Strategy 0: Direct JSON API (no HTML parsing needed)
                tag_slug = url.split("/tags/")[-1].rstrip("/") if "/tags/" in url else _LAND_TAG
                city_arg = label if label != "national" else ""
                posts = self._fetch_api(tag_slug, city_arg)
                if posts:
                    logger.debug(f"[haraj] [{label}]: JSON API gave {len(posts)} posts")
                else:
                    # Strategy 1: Turbo-stream SSR
                    resp = self._client.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"Haraj [{label}]: HTTP {resp.status_code}")
                        time.sleep(1.0)
                        continue

                    arr = _extract_turbo_array(resp.text)
                    if arr is not None:
                        posts = _extract_posts(arr)
                        logger.debug(f"[haraj] [{label}]: turbo-stream gave {len(posts)} posts")
                    else:
                        # Strategy 2: BeautifulSoup HTML card parsing
                        logger.info(f"[haraj] [{label}]: turbo-stream not found — trying HTML fallback")
                        posts = _extract_posts_html(resp.text)

                if not posts:
                    logger.warning(f"Haraj [{label}]: no posts extracted from page")
                    time.sleep(1.0)
                    continue

                new_count = 0
                consecutive_known = 0
                stop_early = False

                for post in posts:
                    pid = post.get("id")
                    if pid in seen_ids:
                        continue

                    city = post.get("city") or post.get("geoCity") or ""
                    if not _city_in_targets(city):
                        # For national tag keep posts even without city (city may be in body)
                        if label != "national":
                            continue

                    price_raw = post.get("price")
                    price = float(price_raw) if isinstance(price_raw, (int, float)) and price_raw > 0 else 0.0
                    if not price:
                        body = post.get("bodyTEXT") or ""
                        area_hint = _area_from_text(body)
                        price = _price_from_text(body, area_hint)
                    if price and not (PRICE_MIN <= price <= PRICE_MAX):
                        continue

                    lid = f"haraj_{pid}"
                    if listing_exists(lid):
                        consecutive_known += 1
                        if consecutive_known >= _EARLY_STOP:
                            logger.info(f"Haraj [{label}]: {_EARLY_STOP} consecutive known — stopping early")
                            stop_early = True
                            break
                        continue

                    consecutive_known = 0
                    seen_ids.add(pid)
                    all_items.append(post)
                    new_count += 1

                logger.info(f"Haraj [{label}]: {new_count} new listings ({len(posts)} parsed)")

                if stop_early:
                    time.sleep(1.0)
                    continue

            except Exception as exc:
                logger.error(f"Haraj [{label}] error: {exc}", exc_info=True)

            time.sleep(1.0)

        logger.info(f"Haraj scraper done — {len(all_items)} total unique listings")
        return all_items

    def normalize(self, raw: dict) -> dict:
        re_info = raw.get("realEstateInfo") or {}
        body    = raw.get("bodyTEXT") or ""

        # Area: structured field first, then regex fallback
        area = float(re_info.get("re_Area") or 0)
        if not area:
            area = _area_from_text(body)

        # Images
        images = raw.get("imagesList") or []
        if isinstance(images, str):
            images = [images] if images else []

        # URL: Haraj stores the relative path; prepend base
        url_path = raw.get("URL") or ""
        if url_path and not url_path.startswith("http"):
            source_url = f"{_BASE}/{url_path.lstrip('/')}"
        else:
            source_url = url_path or f"{_BASE}/{raw.get('id', '')}"

        price_raw = raw.get("price")
        price_sar = float(price_raw) if isinstance(price_raw, (int, float)) and price_raw > 0 else 0.0
        if not price_sar:
            price_sar = _price_from_text(body, area)

        return {
            "listing_id":    f"haraj_{raw.get('id', '')}",
            "source":        self.name,
            "title":         raw.get("title") or "عقار حراج",
            "city":          _normalise_city(raw.get("city") or raw.get("geoCity") or "") or "غير محدد",
            "district":      raw.get("geoNeighborhood") or raw.get("geoCity") or "",
            "area_sqm":      area,
            "price_sar":     price_sar,
            "contact_phone": _phone_from_text(body),
            "image_urls":    ",".join(images[:5]),
            "source_url":    source_url,
            "raw_text":      body,
            "scraped_at":    datetime.now(),
            "_re_info":      re_info,
        }
