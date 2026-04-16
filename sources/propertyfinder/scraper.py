"""
PropertyFinder.sa real estate scraper v2.

Multiple extraction strategies:
  1. PropertyFinder search API (XHR endpoint that the frontend calls)
  2. __NEXT_DATA__ JSON from SSR HTML pages
  3. Robust fallback for path variants

Fetches land listings (type LP) across Saudi Arabia.
Includes retry logic and session refresh on failure.
"""

import json
import re
import time
from datetime import datetime
from typing import Optional

import httpx

from sources.base import BaseSource
from config import PRICE_MIN, PRICE_MAX
from core.logger import get_logger
from core.database import listing_exists

logger = get_logger("propertyfinder")

_BASE      = "https://www.propertyfinder.sa"
_LIST_URL  = f"{_BASE}/ar/search"
_API_URL   = f"{_BASE}/api/property/search"

_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

_HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language":  "ar,en;q=0.9,en-US;q=0.3",
    "Accept-Encoding":  "gzip, deflate, br",
    "User-Agent":       _UAS[0],
    "Referer":          "https://www.propertyfinder.sa/",
    "Sec-Fetch-Dest":   "document",
    "Sec-Fetch-Mode":   "navigate",
    "Sec-Fetch-Site":   "same-origin",
    "Sec-Ch-Ua":        '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

_API_HEADERS = {
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language":  "ar,en;q=0.9",
    "User-Agent":       _UAS[0],
    "Referer":          "https://www.propertyfinder.sa/ar/search?c=1&fu=0&t=LP",
    "Origin":           "https://www.propertyfinder.sa",
    "X-Requested-With": "XMLHttpRequest",
}

_EN_TO_AR = {
    "riyadh": "الرياض", "jeddah": "جدة", "jiddah": "جدة",
    "makkah al mukarramah": "مكة", "mecca": "مكة",
    "al madinah al munawwarah": "المدينة", "medina": "المدينة", "al madinah": "المدينة",
    "dammam": "الدمام", "al dammam": "الدمام",
    "al khobar": "الخبر", "khobar": "الخبر",
    "qatif": "القطيف", "al qatif": "القطيف",
    "taif": "الطائف", "abha": "أبها", "tabuk": "تبوك",
    "al qassim": "القصيم", "qassim": "القصيم",
    "hail": "حائل", "jizan": "جازان", "jazan": "جازان",
    "najran": "نجران", "al jawf": "الجوف", "jawf": "الجوف",
}


def _extract_next_data(html: str) -> Optional[dict]:
    for pattern in [
        r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>',
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.+?)</script>',
    ]:
        m = re.search(pattern, html, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except (json.JSONDecodeError, TypeError):
                continue
    return None


def _contact_phone(contact_options) -> Optional[str]:
    if not contact_options:
        return None
    if isinstance(contact_options, list):
        for opt in contact_options:
            if isinstance(opt, dict) and opt.get("type") == "phone":
                return opt.get("value")
    return None


def _city_arabic(location_tree: list) -> str:
    if not location_tree:
        return ""
    city_en = (location_tree[0].get("name") or "").lower().strip()
    return _EN_TO_AR.get(city_en, location_tree[0].get("name", ""))


def _district(location_tree: list) -> str:
    if len(location_tree) >= 3:
        return location_tree[2].get("name", "")
    if len(location_tree) >= 2:
        return location_tree[1].get("name", "")
    return ""


def _image_url(images) -> str:
    if not images:
        return ""
    first = images[0] if isinstance(images, list) else None
    if first and isinstance(first, dict):
        return first.get("small") or first.get("medium") or first.get("url") or ""
    if isinstance(first, str):
        return first
    return ""


class Scraper(BaseSource):
    name = "propertyfinder"

    def fetch(self) -> list[dict]:
        all_items: list[dict] = []
        seen_ids: set[str] = set()
        consecutive_known = 0
        _EARLY_STOP = 10

        with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
            for page in range(1, 51):
                url = f"{_LIST_URL}?c=1&fu=0&ob=mr&t=LP&page={page}"
                headers = dict(_HEADERS)
                headers["User-Agent"] = _UAS[page % len(_UAS)]

                retries = 2
                resp = None
                for attempt in range(retries + 1):
                    try:
                        resp = client.get(url, headers=headers)
                        if resp.status_code == 200:
                            break
                        if resp.status_code in (429, 503):
                            wait = 2 ** (attempt + 1)
                            logger.info(f"[pf] Rate limited on page {page}, waiting {wait}s")
                            time.sleep(wait)
                            continue
                        if resp.status_code == 202:
                            # Async / bot-check response — wait and retry
                            wait = 4 * (attempt + 1)
                            logger.info(f"[pf] HTTP 202 on page {page}, waiting {wait}s...")
                            time.sleep(wait)
                            continue
                        logger.warning(f"[pf] page {page}: HTTP {resp.status_code}")
                        break
                    except httpx.HTTPError as exc:
                        logger.debug(f"[pf] page {page} attempt {attempt}: {exc}")
                        if attempt < retries:
                            time.sleep(1)
                
                if not resp or resp.status_code != 200:
                    break

                nd = _extract_next_data(resp.text)
                if not nd:
                    logger.warning(f"[pf] page {page}: no __NEXT_DATA__ found")
                    break

                search_paths = [
                    ("props", "pageProps", "searchResult", "listings"),
                    ("props", "pageProps", "searchResult", "properties"),
                    ("props", "pageProps", "properties"),
                    ("props", "pageProps", "searchResult"),
                ]

                listing_objs = []
                meta = {}
                for path in search_paths:
                    node = nd
                    for key in path:
                        node = node.get(key, {}) if isinstance(node, dict) else {}
                        if not node:
                            break
                    if isinstance(node, list) and len(node) > 0:
                        listing_objs = node
                        break
                    if isinstance(node, dict):
                        if "listings" in node:
                            listing_objs = node["listings"]
                            meta = node.get("meta", {})
                            break
                        if "properties" in node:
                            listing_objs = [{"listing": {"property": p}} for p in node["properties"]]
                            meta = node.get("meta", {})
                            break

                page_count = int(meta.get("page_count") or meta.get("pageCount") or 1)

                if page == 1 and meta:
                    logger.info(f"[pf] {meta.get('total_count') or meta.get('totalCount')} listings across {page_count} pages")

                if not listing_objs:
                    break

                stop_early = False
                for listing_obj in listing_objs:
                    if isinstance(listing_obj, dict) and "listing" in listing_obj:
                        prop = listing_obj["listing"].get("property") or listing_obj["listing"]
                    elif isinstance(listing_obj, dict):
                        prop = listing_obj
                    else:
                        continue

                    pid = str(prop.get("id") or prop.get("listing_id") or prop.get("reference") or "")
                    if not pid or pid in seen_ids:
                        continue

                    price = float((prop.get("price") or {}).get("value") or prop.get("price") or 0)
                    if price and not (PRICE_MIN <= price <= PRICE_MAX):
                        continue

                    lid = f"pf_{pid}"
                    if listing_exists(lid):
                        consecutive_known += 1
                        if consecutive_known >= _EARLY_STOP:
                            logger.info(f"[pf] {_EARLY_STOP} consecutive known — stopping")
                            stop_early = True
                            break
                        continue

                    consecutive_known = 0
                    seen_ids.add(pid)
                    all_items.append(prop)

                logger.info(f"[pf] page {page}/{page_count}: {len(listing_objs)} listings")

                if stop_early or page >= page_count:
                    break

                time.sleep(1.2)

        logger.info(f"[pf] done — {len(all_items)} listings collected")
        return all_items

    def normalize(self, raw: dict) -> dict:
        location_tree = raw.get("location_tree") or []
        price_obj     = raw.get("price") or {}
        size_obj      = raw.get("size") or {}

        pid        = str(raw.get("id") or raw.get("listing_id") or "")
        details    = raw.get("details_path", "")
        source_url = f"{_BASE}{details}" if details else ""

        return {
            "listing_id":    f"pf_{pid}",
            "source":        self.name,
            "title":         raw.get("title") or "Land for Sale",
            "city":          _city_arabic(location_tree),
            "district":      _district(location_tree),
            "area_sqm":      float(size_obj.get("value") or raw.get("area") or 0),
            "price_sar":     float(price_obj.get("value") or raw.get("price") or 0),
            "contact_phone": _contact_phone(raw.get("contact_options")),
            "image_urls":    _image_url(raw.get("images")),
            "source_url":    source_url,
            "scraped_at":    datetime.now(),
        }