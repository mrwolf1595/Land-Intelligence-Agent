"""
Sakan.co Saudi Arabia scraper v2.

Multiple extraction strategies with automatic fallback:
  1. Try internal search API (JSON endpoint)
  2. __NEXT_DATA__ from SSR HTML
  3. HTML card scraping with robust selectors

Filters for land listings in TARGET_CITIES within PRICE_MIN..PRICE_MAX.
"""

import json
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote

import httpx

from sources.base import BaseSource
from config import TARGET_CITIES, PRICE_MIN, PRICE_MAX
from core.logger import get_logger
from core.database import listing_exists

logger = get_logger("sakan")

_BASE = "https://sa.sakan.co"
_SEARCH = f"{_BASE}/ar/sale"          # /ar/properties/sale returns 404 — use /ar/sale
_API_SEARCH = f"{_BASE}/api/search"   # try both /api/search and /api/properties/search
_PER_PAGE = 21
_MAX_PAGES = 30
_EARLY_STOP = 10

_LAND_KEYWORDS = {"أرض", "ارض", "land", "أراضي"}

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_HEADERS = {
    "User-Agent":      _UA,
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.5",
    "Referer":         "https://sa.sakan.co/ar/sale",
}

_API_HEADERS = {
    "User-Agent":      _UA,
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "ar,en;q=0.5",
    "Referer":         "https://sa.sakan.co/ar/sale",
    "X-Requested-With": "XMLHttpRequest",
}


def _parse_price(text) -> float:
    if not text:
        return 0.0
    if isinstance(text, (int, float)):
        return float(text)
    nums = re.findall(r"[\d,]+", str(text).replace("\xa0", ""))
    return float(nums[0].replace(",", "")) if nums else 0.0


def _parse_area(text) -> float:
    if not text:
        return 0.0
    m = re.search(r"([\d,.]+)", str(text))
    return float(m.group(1).replace(",", "")) if m else 0.0


def _city_matches(location: str) -> bool:
    if not location or not TARGET_CITIES:
        return True
    loc = location.replace("-", " ").strip()
    return any(city in loc or loc in city for city in TARGET_CITIES)


def _extract_next_data(html: str) -> Optional[dict]:
    """Parse __NEXT_DATA__ JSON from page HTML."""
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if not m:
        m = re.search(r'<script[^>]*>self\.__next_f\.push\(\[.*?"props":\{.*?\}\]\)</script>', html)
    if m:
        try:
            return json.loads(m.group(1))
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def _parse_api_response(data: dict) -> list[dict]:
    """Parse JSON API response into listing dicts."""
    items = []

    props = data.get("data") or data.get("properties") or data.get("listings") or []
    if isinstance(data.get("data"), dict):
        props = data["data"].get("properties") or data["data"].get("listings") or data["data"].get("items") or []

    for prop in props:
        if isinstance(prop, dict):
            items.append(prop)
    return items


def _parse_html_cards(html: str) -> list[dict]:
    """Parse listing cards from HTML using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("[sakan] beautifulsoup4 not installed")
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_refs = set()

    card_selectors = [
        "div[class*='property-card']",
        "div[class*='listing-card']",
        "div[class*='PropertyCard']",
        "article[class*='property']",
        "div[class*='card']",
        "a[class*='property']",
    ]

    cards = []
    for sel in card_selectors:
        found = soup.select(sel)
        if found:
            cards = found
            break

    if not cards:
        cards = soup.find_all("a", href=re.compile(r"/ar/properties/"))

    for card in cards:
        try:
            link = card if card.name == "a" else card.find("a", href=True)
            if not link or not link.get("href"):
                continue

            href = link["href"]
            detail_url = href if href.startswith("http") else _BASE + href

            ref_match = re.search(r"-(\d+)/?$", detail_url)
            if not ref_match:
                ref_match = re.search(r"/(\d+)", detail_url)
            if not ref_match:
                continue

            ref_id = ref_match.group(1)
            if ref_id in seen_refs:
                continue
            seen_refs.add(ref_id)

            title = ""
            for tag in card.select("h2, h3, [class*='title'], [class*='Title']"):
                title = tag.get_text(strip=True)
                if title:
                    break

            price = 0.0
            price_el = card.select_one("[class*='price'], [class*='Price']")
            if price_el:
                price = _parse_price(price_el.get_text())

            location = ""
            for loc_el in card.select("[class*='location'], [class*='Location'], [class*='area'], [class*='address']"):
                loc_text = loc_el.get_text(strip=True)
                if loc_text:
                    location = loc_text
                    break

            area_sqm = 0.0
            for amenity in card.select("[class*='amenity'], [class*='feature'], [class*='detail'], span, div"):
                t = amenity.get_text()
                if t and ("m²" in t or "م²" in t or "متر" in t):
                    area_sqm = _parse_area(t)
                    if area_sqm > 0:
                        break

            items.append({
                "ref_id": ref_id,
                "title": title or "عقار للبيع",
                "price": price,
                "location": location,
                "area_sqm": area_sqm,
                "url": detail_url,
            })
        except Exception as e:
            logger.debug(f"[sakan] card parse error: {e}")
            continue

    return items


class Scraper(BaseSource):
    name = "sakan"

    def __init__(self):
        self._client = httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True)

    def fetch(self) -> list[dict]:
        all_items: list[dict] = []
        seen_refs: set = set()
        consecutive_known = 0

        items = self._fetch_api()
        if items is not None:
            logger.info(f"[sakan] API: {len(items)} listings")
            for item in items:
                ref_id = str(item.get("id") or item.get("ref_id") or "")
                if not ref_id or ref_id in seen_refs:
                    continue
                lid = f"sakan_{ref_id}"
                if listing_exists(lid):
                    consecutive_known += 1
                    if consecutive_known >= _EARLY_STOP:
                        break
                    continue
                consecutive_known = 0
                seen_refs.add(ref_id)

                price = float(item.get("price") or item.get("price_sar") or item.get("salePrice") or 0)
                if price and not (PRICE_MIN <= price <= PRICE_MAX):
                    continue

                location = item.get("city") or item.get("location") or ""
                if not _city_matches(location):
                    continue

                all_items.append(item)

            if all_items:
                logger.info(f"[sakan] API done — {len(all_items)} new listings")
                return all_items

        for page in range(1, _MAX_PAGES + 1):
            url = f"{_SEARCH}?page={page}" if page > 1 else _SEARCH
            try:
                resp = self._client.get(url, headers=_HEADERS)
                if resp.status_code == 403:
                    logger.warning(f"[sakan] page {page}: HTTP 403 — blocked")
                    break
                if resp.status_code != 200:
                    logger.warning(f"[sakan] page {page}: HTTP {resp.status_code}")
                    break
            except Exception as e:
                logger.error(f"[sakan] page {page}: {e}")
                break

            html = resp.text

            nd = _extract_next_data(html)
            if nd:
                props = (
                    nd.get("props", {})
                    .get("pageProps", {})
                    .get("searchResult", {})
                    .get("properties") or
                    nd.get("props", {})
                    .get("pageProps", {})
                    .get("properties") or []
                )
                if props:
                    for prop in props:
                        ref_id = str(prop.get("id") or prop.get("ref_id") or "")
                        if not ref_id or ref_id in seen_refs:
                            continue
                        seen_refs.add(ref_id)
                        lid = f"sakan_{ref_id}"
                        if listing_exists(lid):
                            consecutive_known += 1
                            if consecutive_known >= _EARLY_STOP:
                                break
                            continue
                        consecutive_known = 0

                        price = _parse_price(prop.get("price") or (prop.get("priceInfo") or {}).get("value"))
                        if price and not (PRICE_MIN <= price <= PRICE_MAX):
                            continue

                        location = prop.get("city") or prop.get("location") or ""
                        if not _city_matches(location):
                            continue

                        all_items.append(prop)
                    logger.info(f"[sakan] page {page} (__NEXT_DATA__): found listings")
                    continue

            cards = _parse_html_cards(html)
            if not cards:
                logger.info(f"[sakan] page {page}: no listings found")
                break

            for card in cards:
                ref_id = card.get("ref_id", "")
                if ref_id in seen_refs:
                    continue
                seen_refs.add(ref_id)

                lid = f"sakan_{ref_id}"
                if listing_exists(lid):
                    consecutive_known += 1
                    if consecutive_known >= _EARLY_STOP:
                        break
                    continue
                consecutive_known = 0

                price = card.get("price", 0.0)
                if price and not (PRICE_MIN <= price <= PRICE_MAX):
                    continue
                if not _city_matches(card.get("location", "")):
                    continue

                all_items.append(card)

            logger.info(f"[sakan] page {page} (HTML): {len(cards)} cards")

            if consecutive_known >= _EARLY_STOP:
                break

            time.sleep(1.5)

        logger.info(f"[sakan] done — {len(all_items)} new listings")
        return all_items

    def _fetch_api(self) -> Optional[list[dict]]:
        """Try the JSON search API endpoint (tries multiple paths)."""
        api_candidates = [
            f"{_BASE}/api/search",
            f"{_BASE}/api/properties/search",
            f"{_BASE}/api/v1/properties",
        ]
        for base_url in api_candidates:
            results = []
            try:
                resp = self._client.get(
                    f"{base_url}?page=1&per_page=50&for=sale&type=land",
                    headers=_API_HEADERS,
                )
                if resp.status_code in (401, 403, 404):
                    logger.debug(f"[sakan] API {base_url}: HTTP {resp.status_code} — skip")
                    continue
                if resp.status_code not in (200, 201):
                    logger.debug(f"[sakan] API {base_url}: HTTP {resp.status_code}")
                    continue
                data = resp.json()
                props = _parse_api_response(data)
                if not props:
                    continue
                results.extend(props)
                # Got results from this endpoint — fetch remaining pages
                for page in range(2, 4):
                    try:
                        r2 = self._client.get(
                            f"{base_url}?page={page}&per_page=50&for=sale&type=land",
                            headers=_API_HEADERS,
                        )
                        if r2.status_code not in (200, 201):
                            break
                        results.extend(_parse_api_response(r2.json()))
                    except Exception:
                        break
                logger.info(f"[sakan] API {base_url}: {len(results)} total listings")
                return results if results else None
            except Exception as e:
                logger.debug(f"[sakan] API {base_url} error: {e}")
                continue
        return None

    def normalize(self, raw: dict) -> dict:
        location = raw.get("location") or raw.get("city") or ""
        city = "غير محدد"
        district = ""
        if isinstance(location, str):
            if "،" in location:
                parts = [p.strip() for p in location.split("،")]
                city = parts[-1] if parts else location
                district = parts[0] if len(parts) > 1 else ""
            elif location:
                city = location
        elif isinstance(location, dict):
            city = location.get("name") or location.get("city") or "غير محدد"
            district = location.get("district") or ""

        area_sqm = float(raw.get("area_sqm") or raw.get("area") or raw.get("size", {}).get("value") or 0)
        if not area_sqm:
            area_text = raw.get("area_text") or ""
            area_sqm = _parse_area(area_text)

        price = _parse_price(raw.get("price") or raw.get("price_sar") or raw.get("salePrice") or 0)

        ref_id = str(raw.get("id") or raw.get("ref_id") or "")
        url = raw.get("url") or raw.get("source_url") or ""
        if not url and ref_id:
            url = f"{_BASE}/ar/property/{ref_id}"

        return {
            "listing_id":    f"sakan_{raw.get('ref_id') or ref_id}",
            "source":        self.name,
            "title":         raw.get("title") or "عقار للبيع",
            "city":          city,
            "district":      district or raw.get("district") or "",
            "area_sqm":      area_sqm,
            "price_sar":     price,
            "contact_phone": raw.get("phone") or raw.get("contact"),
            "contact_name":  None,
            "image_urls":     raw.get("image_urls") or raw.get("images") or "",
            "source_url":    url or _BASE,
            "scraped_at":    datetime.now(),
        }