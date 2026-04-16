"""
Aqar.fm GraphQL scraper (sa.aqar.fm).
Uses cloudscraper to bypass anti-bot, queries the GraphQL endpoint directly.
Falls back to httpx if cloudscraper is not installed.

API note (2025): schema changed — now uses Search.find / WhereInput.
"""

import time
from datetime import datetime
from typing import Optional

try:
    import cloudscraper
    _HAS_CLOUDSCRAPER = True
except ImportError:
    _HAS_CLOUDSCRAPER = False
    import httpx

from config import PRICE_MAX, PRICE_MIN, TARGET_CITIES
from core.logger import get_logger
from core.database import listing_exists
from sources.base import BaseSource

logger = get_logger("aqar")

_BASE       = "https://sa.aqar.fm"
_GQL        = f"{_BASE}/graphql"
_PAGE_SIZE  = 50
_MAX_PAGES  = 20
_EARLY_STOP = 10

_HEADERS = {
    "Accept":             "application/json",
    "Accept-Language":    "ar,en;q=0.5",
    "Content-Type":       "application/json",
    "Req-App":            "Web",
    "Req-Device-Token":   "12e262b6-e799-46f1-8e42-252002be2900",
    "App-Version":        "0.20.46",
    "Origin":             _BASE,
    "Referer":            f"{_BASE}/",
}

# New API (2025): Search.find with WhereInput
_FIND_LISTINGS_QUERY = """
query Search($size: Int, $from: Int, $sort: SortInput, $where: WhereInput) {
  Search {
    find(size: $size, from: $from, sort: $sort, where: $where) {
      listings {
        id
        area
        price
        city
        district
        title
        path
        uri
        address
        meter_price
        user {
          phone
          name
        }
        location {
          lat
          lng
        }
      }
    }
  }
}
"""

# Legacy API (fallback): direct findListings
_FIND_LISTINGS_LEGACY = """
query findListings($size: Int, $from: Int, $sort: SortInput, $where: ListingWhereInput) {
  findListings(size: $size, from: $from, sort: $sort, where: $where) {
    id
    area
    price
    city
    district
    title
    path
    uri
    address
    meter_price
    user {
      phone
      name
    }
    location {
      lat
      lng
    }
  }
}
"""

_GET_CITIES_QUERY = """
query getAllCities($input: GetAllCitiesInput) {
  getAllCities(input: $input) {
    name
    city_id
    count
  }
}
"""


def _make_session():
    """Return a cloudscraper session (or httpx.Client as fallback)."""
    if _HAS_CLOUDSCRAPER:
        session = cloudscraper.create_scraper(browser={"browser": "firefox", "platform": "linux", "mobile": False})
        session.headers.update(_HEADERS)
        return session
    else:
        logger.warning("[aqar] cloudscraper not available — using httpx (may be blocked)")
        return httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True)


def _post(session, payload: dict) -> Optional[dict]:
    """POST GraphQL query, return parsed JSON or None."""
    try:
        if _HAS_CLOUDSCRAPER:
            resp = session.post(_GQL, json=payload, timeout=30)
        else:
            resp = session.post(_GQL, json=payload)
        if resp.status_code == 400:
            # Log the actual error from the server for debugging
            try:
                err = resp.json()
                logger.error(f"[aqar] GraphQL 400: {err.get('errors', err)}")
            except Exception:
                logger.error(f"[aqar] GraphQL 400: {resp.text[:300]}")
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.error(f"[aqar] GraphQL request failed: {exc}")
        return None


def _extract_listings(data: dict) -> list:
    """Extract listing list from GraphQL response — handles both new and legacy schema."""
    if not data:
        return []
    d = data.get("data", {})
    # New schema: data.Search.find.listings
    if "Search" in d:
        return d["Search"].get("find", {}).get("listings") or []
    # Legacy schema: data.findListings
    if "findListings" in d:
        return d["findListings"] or []
    return []


def _fetch_cities(session) -> list[dict]:
    """Fetch all available cities from Aqar."""
    payload = {
        "operationName": "getAllCities",
        "query": _GET_CITIES_QUERY,
        "variables": {"input": {"category": 0}},
    }
    data = _post(session, payload)
    if not data:
        return []
    d = data.get("data", {})
    return d.get("getAllCities") or []


def _city_matches(city_name: str) -> bool:
    if not city_name or not TARGET_CITIES:
        return True
    name = city_name.strip()
    return any(t in name or name in t for t in TARGET_CITIES)


class Scraper(BaseSource):
    name = "aqar"

    def fetch(self) -> list[dict]:
        all_items: list[dict] = []
        seen_ids:  set[str]   = set()

        session = _make_session()

        # Detect which query works: new API first, fallback to legacy
        query_to_use   = _FIND_LISTINGS_QUERY
        op_name        = "Search"
        use_legacy     = False

        try:
            # Fetch city list, then filter to TARGET_CITIES
            cities = _fetch_cities(session)
            if not cities:
                logger.warning("[aqar] Could not fetch city list — scraping without city filter")
                cities = [{"name": c, "city_id": None} for c in TARGET_CITIES]
            else:
                if TARGET_CITIES:
                    cities = [c for c in cities if _city_matches(c.get("name", ""))]
                logger.info(f"[aqar] Scraping {len(cities)} cities")

            for city_obj in cities:
                city_id   = city_obj.get("city_id")
                city_name = city_obj.get("name", "")
                consecutive_known = 0

                for page_idx in range(_MAX_PAGES):
                    from_offset = page_idx * _PAGE_SIZE

                    where: dict = {
                        "category": {"eq": 17},
                        "type":     {"eq": 1},
                    }
                    if city_id is not None:
                        where["city_id"] = {"eq": city_id}

                    payload = {
                        "operationName": op_name,
                        "query": query_to_use,
                        "variables": {
                            "size": _PAGE_SIZE,
                            "from": from_offset,
                            "sort": {"create_time": "desc"},
                            "where": where,
                        },
                    }

                    data = _post(session, payload)

                    # If new API failed on first city first page, try legacy
                    if data is None and not use_legacy and page_idx == 0 and city_obj is cities[0]:
                        logger.info("[aqar] New API failed — retrying with legacy query")
                        use_legacy   = True
                        query_to_use = _FIND_LISTINGS_LEGACY
                        op_name      = "findListings"
                        payload["operationName"] = op_name
                        payload["query"]         = query_to_use
                        data = _post(session, payload)

                    if not data:
                        break

                    listings = _extract_listings(data)
                    if not listings:
                        break

                    new_on_page = 0
                    stop_city   = False

                    for listing in listings:
                        eid = str(listing.get("id", ""))
                        if not eid or eid in seen_ids:
                            continue
                        seen_ids.add(eid)

                        lid = f"aqar_{eid}"
                        if listing_exists(lid):
                            consecutive_known += 1
                            if consecutive_known >= _EARLY_STOP:
                                logger.info(f"[aqar] {city_name}: early stop ({_EARLY_STOP} consecutive known)")
                                stop_city = True
                                break
                            continue

                        consecutive_known = 0

                        price = float(listing.get("price") or 0)
                        if price and not (PRICE_MIN <= price <= PRICE_MAX):
                            continue

                        all_items.append(listing)
                        new_on_page += 1

                    logger.info(f"[aqar] {city_name} page {page_idx}: {new_on_page} new listings")

                    if stop_city or len(listings) < _PAGE_SIZE:
                        break

                    time.sleep(0.8)

        finally:
            try:
                session.close()
            except Exception:
                pass

        logger.info(f"[aqar] done — {len(all_items)} total new listings")
        return all_items

    def normalize(self, raw: dict) -> dict:
        eid  = str(raw.get("id", ""))
        path = raw.get("path") or raw.get("uri") or ""
        if path and not path.startswith("http"):
            source_url = f"{_BASE}{path}"
        elif path:
            source_url = path
        else:
            source_url = ""

        user = raw.get("user") or {}

        return {
            "listing_id":    f"aqar_{eid}",
            "source":        self.name,
            "title":         raw.get("title") or "أرض للبيع",
            "city":          raw.get("city") or "غير محدد",
            "district":      raw.get("district") or "",
            "area_sqm":      float(raw.get("area") or 0),
            "price_sar":     float(raw.get("price") or 0),
            "contact_phone": user.get("phone"),
            "contact_name":  user.get("name"),
            "image_urls":    "",
            "source_url":    source_url,
            "scraped_at":    datetime.now(),
        }
