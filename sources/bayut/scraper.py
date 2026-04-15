"""
Bayut.sa real estate scraper.
Uses Bayut's Algolia search backend (reverse-engineered from browser runtime).

Endpoint : https://LL8IZ711CS-dsn.algolia.net/1/indexes/{index}/query
Index    : bayut-sa-production-ads-city-level-score-ar
Filter   : purpose:for-sale AND category.slug_l1:residential-lands
Yield    : ~20 000 land listings across Saudi Arabia with phone numbers
Pagination: page param (0-indexed), hitsPerPage up to 20, Algolia cap = 1000 pages
"""

import time
from datetime import datetime
from typing import Optional

import httpx

from sources.base import BaseSource
from config import TARGET_CITIES, PRICE_MIN, PRICE_MAX
from core.logger import get_logger
from core.database import listing_exists, get_cursor

logger = get_logger("bayut")

# ── Algolia credentials (public browser key — read-only search) ───────────────
_APP_ID   = "LL8IZ711CS"
_API_KEY  = "5b970b39b22a4ff1b99e5167696eef3f"
_INDEX    = "bayut-sa-production-ads-city-level-score-ar"
_ALGOLIA  = f"https://{_APP_ID}-dsn.algolia.net/1/indexes/{_INDEX}/query"

_HEADERS = {
    "X-Algolia-Application-Id": _APP_ID,
    "X-Algolia-API-Key":        _API_KEY,
    "Content-Type":             "application/json",
    "Referer":                  "https://www.bayut.sa/",
    "Origin":                   "https://www.bayut.sa",
}

_ATTRS = [
    "externalID", "title", "price", "area", "plotArea",
    "location", "geography", "phoneNumber", "contactName",
    "coverPhoto", "slug_l1", "purpose", "category",
    "extraFields", "agency", "createdAt", "updatedAt",
]

_HITS_PER_PAGE = 20
_MAX_PAGES     = 1000   # Algolia hard cap; 20 000 records total


def _city_name(location: list) -> str:
    """Extract city name from Bayut location array (level 1)."""
    for loc in (location or []):
        if loc.get("level") == 1:
            return loc.get("name", "")
    return ""


def _district_name(location: list) -> str:
    """Extract district name from Bayut location array (level 3)."""
    for loc in (location or []):
        if loc.get("level") == 3:
            return loc.get("name", "")
    return ""


def _phone(phone_obj) -> Optional[str]:
    """Extract first available mobile number."""
    if not phone_obj:
        return None
    if isinstance(phone_obj, str):
        return phone_obj
    numbers = phone_obj.get("mobileNumbers") or []
    if numbers:
        return numbers[0]
    return phone_obj.get("mobile") or phone_obj.get("whatsapp")


def _image_url(cover_photo: dict) -> str:
    if not cover_photo:
        return ""
    photo_id = cover_photo.get("id")
    return f"https://images.bayut.sa/thumbnails/{photo_id}-400x300.jpeg" if photo_id else ""


def _city_in_targets(city: str) -> bool:
    if not city:
        return False
    return any(t in city or city in t for t in TARGET_CITIES)


class Scraper(BaseSource):
    name = "bayut"

    def fetch(self) -> list[dict]:
        all_items: list[dict] = []
        seen_ids: set[str] = set()
        page = 0
        consecutive_known = 0
        _EARLY_STOP = 30

        # Build base Algolia query params
        algolia_params: dict = {
            "query":               "",
            "page":                page,
            "hitsPerPage":         _HITS_PER_PAGE,
            "filters":             "purpose:for-sale AND category.slug_l1:residential-lands",
            "attributesToRetrieve": _ATTRS,
        }

        # Incremental: add timestamp filter if we have a previous run
        cursor = get_cursor("bayut")
        last_run_at = cursor.get("last_run_at")
        if last_run_at:
            try:
                ts = int(datetime.fromisoformat(last_run_at).timestamp())
                algolia_params["numericFilters"] = [f"updatedAt > {ts}"]
                logger.info(f"Bayut incremental: filtering updatedAt > {ts} ({last_run_at})")
            except Exception:
                pass

        logger.info(f"Bayut scraper starting — index: {_INDEX}")

        with httpx.Client(headers=_HEADERS, timeout=30) as client:
            while page < _MAX_PAGES:
                algolia_params["page"] = page
                try:
                    resp = client.post(_ALGOLIA, json=algolia_params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.error(f"Bayut page {page} error: {exc}")
                    break

                hits      = data.get("hits", [])
                nb_pages  = data.get("nbPages", 0)
                nb_hits   = data.get("nbHits", 0)

                if page == 0:
                    logger.info(f"Bayut: {nb_hits} total listings across {nb_pages} pages")

                if not hits:
                    break

                for hit in hits:
                    eid = str(hit.get("externalID", ""))
                    if not eid or eid in seen_ids:
                        continue

                    city = _city_name(hit.get("location", []))
                    if not _city_in_targets(city):
                        continue

                    price = float(hit.get("price") or 0)
                    if price and not (PRICE_MIN <= price <= PRICE_MAX):
                        continue

                    lid = f"bayut_{eid}"
                    if listing_exists(lid):
                        consecutive_known += 1
                        if consecutive_known >= _EARLY_STOP:
                            logger.info(f"Bayut: {_EARLY_STOP} consecutive known listings — stopping early")
                            return all_items
                        continue

                    consecutive_known = 0
                    seen_ids.add(eid)
                    all_items.append(hit)

                logger.info(f"  page {page}/{nb_pages}: +{len(hits)} hits, kept running: {len(all_items)}")

                if page >= nb_pages - 1:
                    break

                page += 1
                time.sleep(0.5)

        logger.info(f"Bayut scraper done — {len(all_items)} listings collected")
        return all_items

    def normalize(self, raw: dict) -> dict:
        location = raw.get("location", [])
        extra    = raw.get("extraFields") or {}

        # Prefer REGA-certified city/district names when available
        city     = extra.get("rega_location_city",     {}).get("ar") or _city_name(location)
        district = extra.get("rega_location_district", {}).get("ar") or _district_name(location)

        area = float(raw.get("area") or raw.get("plotArea") or 0)

        slug = raw.get("slug_l1", "")
        source_url = f"https://www.bayut.sa/property/{slug}.html" if slug else ""

        return {
            "listing_id":    f"bayut_{raw.get('externalID', '')}",
            "source":        self.name,
            "title":         raw.get("title", "أرض للبيع"),
            "city":          city,
            "district":      district,
            "area_sqm":      area,
            "price_sar":     float(raw.get("price") or 0),
            "contact_phone": _phone(raw.get("phoneNumber")),
            "contact_name":  raw.get("contactName", ""),
            "image_urls":    _image_url(raw.get("coverPhoto")),
            "source_url":    source_url,
            "scraped_at":    datetime.now(),
        }
