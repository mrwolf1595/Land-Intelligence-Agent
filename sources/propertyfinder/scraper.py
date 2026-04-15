"""
PropertyFinder.sa real estate scraper.
Fetches land listings from the SSR HTML pages (Next.js Pages Router).

Strategy  : GET https://www.propertyfinder.sa/en/buy/land-for-sale.html?page=N
            Parse listing data from __NEXT_DATA__ JSON embedded in the HTML.
Yield     : ~179 listings (all Saudi lands), 25/page, up to 8 pages.
Contact   : phone, whatsapp, and email available directly in the page data.
"""

import json
import re
import time
from datetime import datetime
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from sources.base import BaseSource
from config import PRICE_MIN, PRICE_MAX
from core.logger import get_logger
from core.database import listing_exists

logger = get_logger("propertyfinder")

_BASE     = "https://www.propertyfinder.sa"
_LIST_URL = f"{_BASE}/en/buy/land-for-sale.html"

_HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# English → Arabic city name mapping for TARGET_CITIES matching
_EN_TO_AR: dict[str, str] = {
    "riyadh":                        "الرياض",
    "jeddah":                        "جدة",
    "jiddah":                        "جدة",
    "makkah al mukarramah":          "مكة",
    "mecca":                         "مكة",
    "al madinah al munawwarah":      "المدينة",
    "medina":                        "المدينة",
    "al madinah":                    "المدينة",
    "dammam":                        "الدمام",
    "al dammam":                     "الدمام",
    "al khobar":                     "الخبر",
    "khobar":                        "الخبر",
    "qatif":                         "القطيف",
    "al qatif":                      "القطيف",
    "taif":                          "الطائف",
    "abha":                          "أبها",
    "tabuk":                         "تبوك",
    "al qassim":                     "القصيم",
    "qassim":                        "القصيم",
    "hail":                          "حائل",
    "jizan":                         "جازان",
    "jazan":                         "جازان",
    "najran":                        "نجران",
    "al jawf":                       "الجوف",
    "jawf":                          "الجوف",
}


def _extract_next_data(html: str) -> Optional[dict]:
    """Parse __NEXT_DATA__ JSON from page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        return None
    try:
        return json.loads(tag.string)
    except Exception:
        return None


def _contact_phone(contact_options) -> Optional[str]:
    """Return first phone number from contact_options array."""
    if not contact_options:
        return None
    for opt in contact_options:
        if isinstance(opt, dict) and opt.get("type") == "phone":
            return opt.get("value")
    return None


def _city_arabic(location_tree: list) -> str:
    """Map English city name to Arabic using the location_tree."""
    if not location_tree:
        return ""
    city_en = (location_tree[0].get("name") or "").lower().strip()
    return _EN_TO_AR.get(city_en, location_tree[0].get("name", ""))


def _district(location_tree: list) -> str:
    """Return neighborhood/district (level 2 = area name in Arabic if available)."""
    if len(location_tree) >= 3:
        return location_tree[2].get("name", "")
    if len(location_tree) >= 2:
        return location_tree[1].get("name", "")
    return ""


def _image_url(images) -> str:
    if not images:
        return ""
    first = images[0] if isinstance(images, list) else None
    if first:
        return first.get("small") or first.get("medium") or ""
    return ""


class Scraper(BaseSource):
    name = "propertyfinder"

    def fetch(self) -> list[dict]:
        all_items: list[dict] = []
        seen_ids: set[str] = set()
        page = 1
        consecutive_known = 0
        _EARLY_STOP = 10

        with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
            while True:
                url = _LIST_URL if page == 1 else f"{_LIST_URL}?page={page}"
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"PropertyFinder page {page}: HTTP {resp.status_code}")
                        break

                    nd = _extract_next_data(resp.text)
                    if not nd:
                        logger.warning(f"PropertyFinder page {page}: no __NEXT_DATA__")
                        break

                    sr         = nd.get("props", {}).get("pageProps", {}).get("searchResult", {})
                    properties = sr.get("properties", [])
                    meta       = sr.get("meta", {})
                    page_count = meta.get("page_count", 1)

                    if page == 1:
                        logger.info(f"PropertyFinder: {meta.get('total_count')} listings, {page_count} pages")

                    if not properties:
                        break

                    stop_early = False
                    for prop in properties:
                        pid = str(prop.get("id") or prop.get("listing_id") or "")
                        if not pid or pid in seen_ids:
                            continue

                        price = float((prop.get("price") or {}).get("value") or 0)
                        if price and not (PRICE_MIN <= price <= PRICE_MAX):
                            continue

                        lid = f"pf_{pid}"
                        if listing_exists(lid):
                            consecutive_known += 1
                            if consecutive_known >= _EARLY_STOP:
                                logger.info(f"PropertyFinder: {_EARLY_STOP} consecutive known — stopping early")
                                stop_early = True
                                break
                            continue

                        consecutive_known = 0
                        seen_ids.add(pid)
                        all_items.append(prop)

                    logger.info(f"  page {page}/{page_count}: +{len(properties)} listings")

                    if stop_early or page >= page_count:
                        break

                except Exception as exc:
                    logger.error(f"PropertyFinder page {page} error: {exc}")
                    break

                page += 1
                time.sleep(1.2)

        logger.info(f"PropertyFinder done — {len(all_items)} listings collected")
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
            "title":         raw.get("title", "Land for Sale"),
            "city":          _city_arabic(location_tree),
            "district":      _district(location_tree),
            "area_sqm":      float(size_obj.get("value") or 0),
            "price_sar":     float(price_obj.get("value") or 0),
            "contact_phone": _contact_phone(raw.get("contact_options")),
            "image_urls":    _image_url(raw.get("images")),
            "source_url":    source_url,
            "scraped_at":    datetime.now(),
        }
