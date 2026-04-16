"""
Sakan.co Saudi Arabia scraper v3.

Endpoint: GET https://sa.sakan.co/ar/search/filter
          ?page=N&propertyType=land&purpose=sale&country_id=2
Response: server-rendered HTML with cards using class 'card card-id-XXXXX'

Session cookie from /ar/sale homepage is required for filter to return data.
"""

import re
import time
from datetime import datetime
from typing import Optional

import httpx

from sources.base import BaseSource
from config import TARGET_CITIES, PRICE_MIN, PRICE_MAX
from core.logger import get_logger
from core.database import listing_exists

logger = get_logger("sakan")

_BASE        = "https://sa.sakan.co"
_HOME        = f"{_BASE}/ar/sale"
_FILTER_URL  = f"{_BASE}/ar/search/filter"
_PER_PAGE    = 21
_MAX_PAGES   = 30
_EARLY_STOP  = 10

_UA = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"

_HEADERS = {
    "User-Agent":      _UA,
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.5",
    "Referer":         _HOME,
}

_AJAX_HEADERS = {
    "User-Agent":        _UA,
    "Accept":            "text/html, */*; q=0.01",
    "Accept-Language":   "ar,en;q=0.5",
    "X-Requested-With":  "XMLHttpRequest",
    "Referer":           _HOME,
}


def _parse_price(text: str) -> float:
    if not text:
        return 0.0
    nums = re.findall(r"[\d,]+", text.replace("\xa0", ""))
    return float(nums[0].replace(",", "")) if nums else 0.0


def _parse_area(text: str) -> float:
    if not text:
        return 0.0
    m = re.search(r"([\d,.]+)", text)
    return float(m.group(1).replace(",", "")) if m else 0.0


def _city_matches(location: str) -> bool:
    if not location or not TARGET_CITIES:
        return True
    loc = location.replace("-", " ").strip()
    return any(city in loc or loc in city for city in TARGET_CITIES)


def _parse_cards(html: str) -> list[dict]:
    """Parse listing cards from Sakan filter HTML response."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("[sakan] beautifulsoup4 not installed")
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = []
    seen_ids = set()

    # Cards use class 'card card-id-XXXXX'
    for card in soup.find_all("div", class_=re.compile(r"card-id-\d+")):
        try:
            class_str = " ".join(card.get("class", []))
            id_m = re.search(r"card-id-(\d+)", class_str)
            if not id_m:
                continue
            ref_id = id_m.group(1)
            if ref_id in seen_ids:
                continue
            seen_ids.add(ref_id)

            # Title: h2 inside card__title
            title = ""
            title_el = card.select_one(".card__title h2")
            if title_el:
                title = title_el.get_text(strip=True)

            # URL: first track_link href
            url = f"{_BASE}/ar/property/details/{ref_id}"
            link_el = card.select_one("a.track_link")
            if link_el and link_el.get("href"):
                href = link_el["href"]
                url = href if href.startswith("http") else _BASE + href

            # Price: span inside card__price-sar
            price = 0.0
            price_el = card.select_one(".card__price-sar span")
            if price_el:
                price = _parse_price(price_el.get_text())

            # Location: card__location span
            location = ""
            loc_el = card.select_one(".card__location span")
            if loc_el:
                location = loc_el.get_text(strip=True)

            # Area: amenity item containing m2
            area_sqm = 0.0
            for amenity in card.select(".card__aminities-item span"):
                t = amenity.get_text()
                if "m" in t and any(c.isdigit() for c in t):
                    area_sqm = _parse_area(t)
                    if area_sqm > 0:
                        break

            items.append({
                "ref_id":   ref_id,
                "title":    title or "عقار للبيع",
                "price":    price,
                "location": location,
                "area_sqm": area_sqm,
                "url":      url,
            })
        except Exception as e:
            logger.debug(f"[sakan] card parse error: {e}")
            continue

    return items


class Scraper(BaseSource):
    name = "sakan"

    def fetch(self) -> list[dict]:
        all_items: list[dict] = []
        seen_refs: set = set()
        consecutive_known = 0

        with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
            # Get session cookies from homepage first
            try:
                home_resp = client.get(_HOME)
                cookies = dict(home_resp.cookies)
                logger.debug(f"[sakan] session cookies: {list(cookies.keys())}")
            except Exception as e:
                logger.warning(f"[sakan] couldn't fetch homepage: {e}")
                cookies = {}

            for page in range(1, _MAX_PAGES + 1):
                try:
                    resp = client.get(
                        _FILTER_URL,
                        params={
                            "page":         page,
                            "propertyType": "land",
                            "purpose":      "sale",
                            "country_id":   2,
                        },
                        headers=_AJAX_HEADERS,
                        cookies=cookies,
                    )
                    if resp.status_code == 403:
                        logger.warning(f"[sakan] page {page}: HTTP 403 — blocked")
                        break
                    if resp.status_code != 200:
                        logger.warning(f"[sakan] page {page}: HTTP {resp.status_code}")
                        break
                except Exception as e:
                    logger.error(f"[sakan] page {page}: {e}")
                    break

                cards = _parse_cards(resp.text)
                if not cards:
                    logger.info(f"[sakan] page {page}: no cards found — stopping")
                    break

                new_on_page = 0
                for card in cards:
                    ref_id = card["ref_id"]
                    if ref_id in seen_refs:
                        continue
                    seen_refs.add(ref_id)

                    lid = f"sakan_{ref_id}"
                    if listing_exists(lid):
                        consecutive_known += 1
                        if consecutive_known >= _EARLY_STOP:
                            logger.info(f"[sakan] {_EARLY_STOP} consecutive known — stopping")
                            return all_items
                        continue

                    consecutive_known = 0

                    price = card["price"]
                    if price and not (PRICE_MIN <= price <= PRICE_MAX):
                        continue
                    if not _city_matches(card["location"]):
                        continue

                    all_items.append(card)
                    new_on_page += 1

                logger.info(f"[sakan] page {page}: {len(cards)} cards, {new_on_page} new")

                if len(cards) < _PER_PAGE:
                    break

                time.sleep(1.5)

        logger.info(f"[sakan] done — {len(all_items)} new listings")
        return all_items

    def normalize(self, raw: dict) -> dict:
        ref_id = str(raw.get("ref_id") or "")
        location = raw.get("location") or ""

        city = "غير محدد"
        district = ""
        if location:
            parts = [p.strip() for p in re.split(r"[،,]", location) if p.strip()]
            if parts:
                city = parts[-1]
                district = parts[0] if len(parts) > 1 else ""

        return {
            "listing_id":    f"sakan_{ref_id}",
            "source":        self.name,
            "title":         raw.get("title") or "أرض للبيع",
            "city":          city,
            "district":      district,
            "area_sqm":      float(raw.get("area_sqm") or 0),
            "price_sar":     float(raw.get("price") or 0),
            "contact_phone": None,
            "contact_name":  None,
            "image_urls":    "",
            "source_url":    raw.get("url") or _BASE,
            "scraped_at":    datetime.now(),
        }
