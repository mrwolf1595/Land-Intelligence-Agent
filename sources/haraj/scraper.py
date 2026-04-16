"""
Haraj.com.sa real estate scraper v3.

Multiple extraction strategies with automatic fallback:
  1. Haraj JSON search API (fastest, most reliable)
  2. Turbo-stream SSR parsed from page HTML
  3. HTML card scraping (last resort)

Target: اراضي-للبيع tags + city-specific tags across Saudi Arabia.
"""

import json
import re
import time
from datetime import datetime
from typing import Optional

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
_LAND_TAG  = "اراضي-للبيع"
_CITY_TAG  = "اراضي-للبيع-في-{city}"

_CITY_SLUG = {"مكة": "مكة-المكرمة", "جدة": "جده", "القصيم": "بريدة"}
_CITY_NORM = {"جده": "جدة", "مكه": "مكة", "مكة-المكرمة": "مكة", "المدينة-المنورة": "المدينة", "بريدة": "القصيم"}

_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

_EARLY_STOP = 15
_MAX_PAGES  = 5


def _headers(page: int = 0) -> dict:
    return {
        "Accept":           "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language":  "ar,en;q=0.5",
        "Accept-Encoding":  "gzip, deflate, br",
        "User-Agent":       _UAS[page % len(_UAS)],
        "Referer":          f"{_BASE}/",
        "Sec-Fetch-Dest":   "document",
        "Sec-Fetch-Mode":   "navigate",
        "Sec-Fetch-Site":   "same-origin",
    }


def _city_slug(city: str) -> str:
    return _CITY_SLUG.get(city, city)


def _normalise_city(city: str) -> str:
    c = (city or "").strip()
    return _CITY_NORM.get(c, c)


def _city_in_targets(city: str) -> bool:
    c = _normalise_city((city or "").strip())
    if not c:
        return False
    return any(t in c or c in t for t in TARGET_CITIES)


def _phone_from_text(text: str) -> Optional[str]:
    m = re.search(r"(?:05\d{8}|\+9665\d{8}|009665\d{8})", text or "")
    return m.group(0) if m else None


def _area_from_text(text: str) -> float:
    m = re.search(r"(\d[\d,.]+)\s*م(?:²|2|²)?", text or "")
    if m:
        return float(m.group(1).replace(",", ""))
    return 0.0


def _extract_json_ld(html: str) -> list[dict]:
    """Strategy 1: Extract JSON-LD structured data."""
    items = []
    for match in re.finditer(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    ):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                items.extend(data)
            elif isinstance(data, dict):
                if "@graph" in data:
                    items.extend(data["@graph"])
                else:
                    items.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return items


def _extract_turbo_array(html: str) -> Optional[list]:
    """Strategy 2: Extract turbo-stream array from React Router 7 SSR."""
    for pattern in [
        r'streamController\.enqueue\(\s*("(?:\[.*?\])")\s*\)',
        r'streamController\.enqueue\(\s*(\[.*?\])\s*\)',
    ]:
        for match in re.finditer(pattern, html, re.DOTALL):
            try:
                raw = match.group(1)
                if raw.startswith('"'):
                    raw = json.loads(raw)
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                continue

    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    for s in scripts:
        if "streamController" not in s or "enqueue" not in s or len(s) < 2000:
            continue
        m = re.search(r'streamController\.enqueue\((".*?")\)', s, re.DOTALL)
        if not m:
            continue
        try:
            inner = json.loads(m.group(1))
            return json.loads(inner)
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _resolve(idx: int, arr: list, depth: int = 0):
    if depth > 30:
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
            else:
                real_key = k
            real_val = _resolve(val_ref, arr, depth + 1) if isinstance(val_ref, int) else val_ref
            result[real_key] = real_val
        return result
    if isinstance(v, list):
        return [_resolve(i, arr, depth + 1) if isinstance(i, int) else i for i in v]
    return v


def _turbo_to_posts(arr: list) -> list[dict]:
    items_key_idx = next((i for i, v in enumerate(arr) if v == "items"), None)
    if items_key_idx is None:
        return []

    posts = []
    seen = set()
    for item in arr:
        if not isinstance(item, dict) or f"_{items_key_idx}" not in item:
            continue
        ref = item[f"_{items_key_idx}"]
        if not isinstance(ref, int) or ref < 0:
            continue
        list_obj = arr[ref] if ref < len(arr) else None
        if not isinstance(list_obj, list):
            continue
        for post_ref in list_obj:
            if not isinstance(post_ref, int) or post_ref < 0 or post_ref >= len(arr):
                continue
            post = _resolve(post_ref, arr)
            if isinstance(post, dict) and isinstance(post.get("id"), int) and post["id"] > 100_000:
                pid = post["id"]
                if pid not in seen:
                    seen.add(pid)
                    posts.append(post)
    return posts


def _scrape_html_cards(html: str) -> list[dict]:
    """Strategy 3: Parse HTML cards as last resort."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    soup = BeautifulSoup(html, "html.parser")
    posts = []

    for card in soup.select("[class*='post'], [class*='ad'], [class*='item']"):
        title_el = card.select_one("h2, h3, [class*='title'], [class*='postTitle']")
        price_el = card.select_one("[class*='price'], [class*='Price']")
        body_el = card.select_one("[class*='body'], [class*='desc'], [class*='text']")

        if not title_el and not price_el:
            continue

        link = card.select_one("a[href]")
        url = link.get("href", "") if link else ""
        if url and not url.startswith("http"):
            url = f"{_BASE}/{url.lstrip('/')}"

        id_match = re.search(r"/(\d{6,})", url)
        pid = int(id_match.group(1)) if id_match else 0
        if pid <= 100_000:
            continue

        price = 0.0
        if price_el:
            pm = re.search(r"([\d,]+)", price_el.get_text())
            if pm:
                price = float(pm.group(1).replace(",", ""))

        body = body_el.get_text(" ", strip=True) if body_el else ""

        posts.append({
            "id": pid,
            "title": title_el.get_text(strip=True) if title_el else "",
            "price": price,
            "bodyTEXT": body,
            "URL": url,
            "city": "",
            "geoCity": "",
        })

    return posts


class Scraper(BaseSource):
    name = "haraj"

    def __init__(self):
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    def _get(self, url: str, retries: int = 2) -> Optional[httpx.Response]:
        for attempt in range(retries + 1):
            try:
                headers = _headers(attempt)
                resp = self._client.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp
                if resp.status_code == 429:
                    wait = 2 ** (attempt + 1) + 1
                    logger.warning(f"[haraj] Rate limited (429), waiting {wait}s...")
                    time.sleep(wait)
                    continue
                logger.debug(f"[haraj] HTTP {resp.status_code} on attempt {attempt}")
            except httpx.HTTPError as exc:
                logger.debug(f"[haraj] request error attempt {attempt}: {exc}")
                if attempt < retries:
                    time.sleep(1)
        return None

    def fetch(self) -> list[dict]:
        all_items: list[dict] = []
        seen_ids: set[int] = set()

        tag_urls: list[tuple[str, str]] = [
            ("national", f"{_BASE}/tags/{_LAND_TAG}/"),
        ]
        for city in TARGET_CITIES:
            slug = _city_slug(city)
            tag = _CITY_TAG.format(city=slug)
            from urllib.parse import quote
            tag_urls.append((city, f"{_BASE}/tags/{quote(tag)}/"))

        logger.info(f"[haraj] Scraping {len(tag_urls)} tag pages")

        for label, url in tag_urls:
            items = self._fetch_tag(label, url, seen_ids)
            all_items.extend(items)
            time.sleep(1.0)

        logger.info(f"[haraj] Done — {len(all_items)} total unique listings")
        return all_items

    def _fetch_tag_api(self, tag: str, city: str = "") -> Optional[list[dict]]:
        """Strategy 0: Hit Haraj JSON API directly (fastest, most reliable)."""
        from urllib.parse import quote
        all_posts = []
        for page in range(1, _MAX_PAGES + 1):
            params = {"tag": tag, "page": page}
            if city:
                params["city"] = city
            try:
                resp = self._client.get(_API_TAG, params=params, headers=_headers(page))
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
            # fallback: try search endpoint
            try:
                params = {"query": "أرض للبيع", "page": 1}
                if city:
                    params["city"] = city
                resp = self._client.get(_API_SRCH, params=params, headers=_headers(0))
                if resp.status_code == 200:
                    d = resp.json()
                    all_posts = (
                        d.get("data", {}).get("posts") or
                        d.get("posts") or []
                    )
            except Exception:
                pass

        return all_posts if all_posts else None

    def _fetch_tag(self, label: str, url: str, seen_ids: set[int]) -> list[dict]:
        # Strategy 0: direct JSON API (no HTML parsing needed)
        tag_part = url.split("/tags/")[-1].rstrip("/") if "/tags/" in url else _LAND_TAG
        city_part = label if label != "national" else ""
        posts = self._fetch_tag_api(tag_part, city_part)
        if posts:
            logger.debug(f"[haraj] [{label}] API: {len(posts)} posts")
        else:
            # Strategy 1-3: HTML fallback
            resp = self._get(url)
            if not resp:
                logger.warning(f"[haraj] [{label}] No response")
                return []

            html = resp.text
            posts = []

            turbo_arr = _extract_turbo_array(html)
            if turbo_arr:
                posts = _turbo_to_posts(turbo_arr)
                logger.debug(f"[haraj] [{label}] Turbo-stream: {len(posts)} posts")

            if not posts:
                json_ld_items = _extract_json_ld(html)
                for item in json_ld_items:
                    if isinstance(item, dict) and item.get("@type") in ("Product", "RealEstateListing", "Offer"):
                        posts.append(item)
                if posts:
                    logger.debug(f"[haraj] [{label}] JSON-LD: {len(posts)} items")

            if not posts:
                posts = _scrape_html_cards(html)
                if posts:
                    logger.debug(f"[haraj] [{label}] HTML cards: {len(posts)} items")

            if not posts:
                logger.warning(f"[haraj] [{label}] No posts extracted from any strategy")
                return []

        result = []
        consecutive_known = 0

        for post in posts:
            pid = post.get("id")
            if not isinstance(pid, int) or pid <= 100_000:
                if isinstance(pid, str) and pid.isdigit():
                    pid = int(pid)
                else:
                    continue

            if pid in seen_ids:
                continue

            city = post.get("city") or post.get("geoCity") or post.get("address", {}).get("addressLocality", "")
            if not _city_in_targets(city) and city:
                continue

            price_raw = post.get("price")
            price = float(price_raw) if isinstance(price_raw, (int, float)) and price_raw > 0 else 0.0

            lid = f"haraj_{pid}"
            if listing_exists(lid):
                consecutive_known += 1
                if consecutive_known >= _EARLY_STOP:
                    logger.info(f"[haraj] [{label}] {_EARLY_STOP} consecutive known — stopping")
                    break
                continue

            consecutive_known = 0
            seen_ids.add(pid)
            result.append(post)

        logger.info(f"[haraj] [{label}] {len(result)} new listings ({len(posts)} extracted)")
        return result

    def normalize(self, raw: dict) -> dict:
        re_info = raw.get("realEstateInfo") or {}
        body = raw.get("bodyTEXT") or raw.get("description") or raw.get("text", "")

        area = float(re_info.get("re_Area") or 0)
        if not area:
            area = _area_from_text(body)

        images = raw.get("imagesList") or raw.get("image") or []
        if isinstance(images, str):
            images = [images] if images else []
        elif isinstance(images, dict) and "url" in images:
            images = [images["url"]]

        url_path = raw.get("URL") or raw.get("url") or ""
        if url_path and not url_path.startswith("http"):
            source_url = f"{_BASE}/{url_path.lstrip('/')}"
        else:
            source_url = url_path or f"{_BASE}/{raw.get('id', '')}"

        price_raw = raw.get("price")
        price_sar = float(price_raw) if isinstance(price_raw, (int, float)) and price_raw > 0 else 0.0

        city = raw.get("city") or raw.get("geoCity") or raw.get("address", {}).get("addressLocality", "")

        return {
            "listing_id":    f"haraj_{raw.get('id', '')}",
            "source":        self.name,
            "title":         raw.get("title") or raw.get("name") or "عقار حراج",
            "city":          _normalise_city(city) or "غير محدد",
            "district":      raw.get("geoNeighborhood") or raw.get("district") or "",
            "area_sqm":      area,
            "price_sar":     price_sar,
            "contact_phone": _phone_from_text(body),
            "image_urls":    ",".join(str(i) for i in images[:5]),
            "source_url":    source_url,
            "raw_text":      body,
            "scraped_at":    datetime.now(),
            "_re_info":      re_info,
        }