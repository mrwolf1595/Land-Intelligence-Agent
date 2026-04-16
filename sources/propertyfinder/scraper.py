"""
PropertyFinder.sa real estate scraper.
Fetches land listings from the SSR HTML pages (Next.js Pages Router).

Strategy  : GET https://www.propertyfinder.sa/ar/search?c=1&fu=0&ob=mr&t=LP&page=N
            Parse listing data from __NEXT_DATA__ JSON embedded in the HTML.
            Tries multiple known JSON paths inside pageProps because the structure
            changes between site versions.
Yield     : land listings (type LP) across Saudi Arabia.
Contact   : phone, whatsapp, and email available directly in the page data.
"""

import json
import re
import time
from datetime import datetime
from typing import Optional

import httpx

from sources.base import BaseSource
from config import PRICE_MIN, PRICE_MAX, TARGET_CITIES
from core.logger import get_logger
from core.database import listing_exists

logger = get_logger("propertyfinder")

_BASE     = "https://www.propertyfinder.sa"
_LIST_URL = f"{_BASE}/ar/search"

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
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        tag = soup.find("script", id="__NEXT_DATA__")
        if tag:
            return json.loads(tag.string)
    except Exception:
        pass

    # Fallback: regex extraction
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
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


def _city_in_targets(city_ar: str) -> bool:
    """Check whether the Arabic city name matches any TARGET_CITIES entry."""
    if not city_ar or not TARGET_CITIES:
        return True  # no filter → include all
    city_lower = city_ar.lower()
    for t in TARGET_CITIES:
        if t in city_ar or city_ar in t or t.lower() in city_lower:
            return True
    return False


def _extract_listings_from_nd(nd: dict) -> tuple[list, int]:
    """
    Extract the listings list and page count from __NEXT_DATA__.
    Returns (listings_list, page_count).
    Tries multiple known paths because PropertyFinder's internal structure varies.
    """
    page_props = nd.get("props", {}).get("pageProps", {})

    # Known structure paths tried in order
    search_result = (
        page_props.get("searchResult") or
        page_props.get("data", {}).get("searchResult") or
        page_props.get("initialData", {}).get("searchResult") or
        {}
    )

    # Listing objects can be at different keys
    listing_objs = (
        search_result.get("listings") or
        search_result.get("properties") or
        page_props.get("listings") or
        page_props.get("properties") or
        []
    )

    # Fallback: old path where each element is a flat property dict
    if not listing_objs:
        flat_props = search_result.get("properties") or []
        listing_objs = [{"listing": {"property": p}} for p in flat_props]

    # Page count
    meta = search_result.get("meta") or search_result.get("pagination") or {}
    page_count = int(
        meta.get("page_count") or meta.get("pageCount") or
        meta.get("total_pages") or meta.get("totalPages") or 1
    )

    return listing_objs, page_count


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
                # c=1 for sale, fu=0, ob=mr most recent, t=LP land plot
                url = f"{_LIST_URL}?c=1&fu=0&ob=mr&t=LP&page={page}"
                try:
                    resp = client.get(url)
                    if resp.status_code == 202:
                        # Async / bot-check response — wait and retry once
                        logger.info(f"PropertyFinder page {page}: HTTP 202, waiting 8s...")
                        time.sleep(8)
                        resp = client.get(url)
                    if resp.status_code == 429:
                        logger.info(f"PropertyFinder page {page}: rate limited, waiting 15s...")
                        time.sleep(15)
                        resp = client.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"PropertyFinder page {page}: HTTP {resp.status_code}")
                        break

                    nd = _extract_next_data(resp.text)
                    if not nd:
                        logger.warning(f"PropertyFinder page {page}: no __NEXT_DATA__")
                        break

                    listing_objs, page_count = _extract_listings_from_nd(nd)

                    if page == 1:
                        logger.info(f"PropertyFinder: {page_count} pages")

                    if not listing_objs:
                        logger.warning(f"PropertyFinder page {page}: listing array empty")
                        break

                    stop_early = False
                    for listing_obj in listing_objs:
                        # Support both {listing: {property: ...}} and flat property dict
                        if "listing" in listing_obj:
                            prop = listing_obj["listing"].get("property") or listing_obj["listing"]
                        else:
                            prop = listing_obj

                        pid = str(
                            prop.get("id") or prop.get("listing_id") or
                            prop.get("reference") or prop.get("externalID") or ""
                        )
                        if not pid or pid in seen_ids:
                            continue

                        # Price can be nested or flat
                        price_raw = prop.get("price")
                        if isinstance(price_raw, dict):
                            price = float(price_raw.get("value") or 0)
                        else:
                            price = float(price_raw or 0)

                        if price and not (PRICE_MIN <= price <= PRICE_MAX):
                            continue

                        # City filter
                        location_tree = prop.get("location_tree") or []
                        city_ar = _city_arabic(location_tree)
                        if not _city_in_targets(city_ar):
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

                    logger.info(f"  page {page}/{page_count}: +{len(listing_objs)} listings")

                    if stop_early or page >= page_count:
                        break

                except Exception as exc:
                    logger.error(f"PropertyFinder page {page} error: {exc}", exc_info=True)
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

        price_val = (
            float(price_obj.get("value") or 0)
            if isinstance(price_obj, dict)
            else float(price_obj or 0)
        )

        return {
            "listing_id":    f"pf_{pid}",
            "source":        self.name,
            "title":         raw.get("title", "Land for Sale"),
            "city":          _city_arabic(location_tree),
            "district":      _district(location_tree),
            "area_sqm":      float(size_obj.get("value") if isinstance(size_obj, dict) else size_obj or 0),
            "price_sar":     price_val,
            "contact_phone": _contact_phone(raw.get("contact_options")),
            "image_urls":    _image_url(raw.get("images")),
            "source_url":    source_url,
            "scraped_at":    datetime.now(),
        }
