"""
Aqar web scraper (direct website fetching).
Used when local Aqar DB is not available.
"""

import re
import time
import importlib
from datetime import datetime
from typing import Optional
from urllib.parse import quote, unquote

import httpx

from config import PRICE_MAX, PRICE_MIN, TARGET_CITIES
from core.logger import get_logger
from core.database import listing_exists
from sources.base import BaseSource

logger = get_logger("aqar")

_BASE = "https://sa.aqar.fm"
_CATEGORY = "أراضي-للبيع"

_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.5",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

_CITY_SLUG_MAP = {
    "مكة": "مكة-المكرمة",
    "المدينة": "المدينة-المنورة",
    "القصيم": "بريدة",
}

# Target city aliases used for strict post-parse filtering.
_CITY_ALIASES = {
    "مكة": {"مكة", "مكةالمكرمة"},
    "المدينة": {"المدينة", "المدينةالمنورة"},
    "القصيم": {"القصيم", "بريدة"},
}


def _city_url(city: str) -> str:
    slug = _CITY_SLUG_MAP.get(city, city)
    return f"{_BASE}/{quote(_CATEGORY)}/{quote(slug)}"


def _norm_city(value: str) -> str:
    return (value or "").replace("-", " ").replace(" ", "").strip()


def _city_matches_target(parsed_city: str, target_city: str) -> bool:
    parsed = _norm_city(parsed_city)
    target = _norm_city(target_city)

    # Fast direct check.
    if parsed == target:
        return True

    # Alias-based check for known naming differences.
    target_aliases = _CITY_ALIASES.get(target_city, {target})
    return parsed in target_aliases


def _parse_card(a_tag) -> Optional[dict]:
    href = a_tag.get("href", "")
    id_match = re.search(r"(\d{5,})$", href)
    if not id_match:
        return None

    listing_id = id_match.group(1)
    parts = href.strip("/").split("/")

    city = unquote(parts[1]).replace("-", " ") if len(parts) > 1 else ""
    district = unquote(parts[3]).replace("-", " ") if len(parts) > 3 else ""

    text = a_tag.get_text(separator=" ", strip=True)
    featured = text.startswith("مميز")
    t = text[3:].strip() if featured else text

    price = 0.0
    pm = re.search(r"([\d,]+\.?\d*)\s*§", t)
    if pm:
        price = float(pm.group(1).replace(",", ""))

    area_sqm = 0.0
    am = re.search(r"([\d,]+)\s*م²", t)
    if am:
        area_sqm = float(am.group(1).replace(",", ""))

    title = ""
    tm = re.search(r"أرض[^§]+", t)
    if tm:
        raw = tm.group(0)
        raw = re.sub(r"\s*[\d,]+\.?\d*\s*§.*$", "", raw)
        raw = re.sub(r"\s*[\d,]+\s*م[²]?\s*$", "", raw)
        title = raw.strip()

    img = a_tag.find("img")
    img_src = img.get("src", "") if img else ""

    return {
        "listing_id": listing_id,
        "href": href,
        "city": city,
        "district": district,
        "price": price,
        "area_sqm": area_sqm,
        "title": title or t[:120],
        "img_src": img_src,
        "featured": featured,
    }


class Scraper(BaseSource):
    name = "aqar"

    def fetch(self) -> list[dict]:
        try:
            bs4 = importlib.import_module("bs4")
            BeautifulSoup = bs4.BeautifulSoup
        except Exception:
            logger.error("beautifulsoup4 is not installed; cannot run Aqar web scraping")
            return []

        all_items: list[dict] = []
        seen_ids: set[str] = set()

        with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
            for city in TARGET_CITIES:
                url = _city_url(city)
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"Aqar {city}: HTTP {resp.status_code}")
                        continue

                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = [
                        a for a in soup.find_all("a", href=True)
                        if re.search(r"\d{5,}$", a.get("href", ""))
                    ]

                    new_count = 0
                    consecutive_known = 0
                    _EARLY_STOP = 10
                    for a in cards:
                        item = _parse_card(a)
                        if not item:
                            continue

                        # Keep only listings that belong to the target city for this loop.
                        if not _city_matches_target(item.get("city", ""), city):
                            continue

                        lid = item["listing_id"]
                        if lid in seen_ids:
                            continue

                        if item["price"] and not (PRICE_MIN <= item["price"] <= PRICE_MAX):
                            continue

                        if listing_exists(f"aqar_{lid}"):
                            consecutive_known += 1
                            if consecutive_known >= _EARLY_STOP:
                                logger.info(f"Aqar {city}: {_EARLY_STOP} consecutive known — stopping early")
                                break
                            continue

                        consecutive_known = 0
                        seen_ids.add(lid)
                        all_items.append(item)
                        new_count += 1

                    logger.info(f"Aqar {city}: {new_count} new listings (cards: {len(cards)})")
                except Exception as exc:
                    logger.error(f"Aqar {city} error: {exc}")

                time.sleep(1.0)

        logger.info(f"Aqar scraper done - {len(all_items)} total listings")
        return all_items

    def normalize(self, raw: dict) -> dict:
        return {
            "listing_id": f"aqar_{raw['listing_id']}",
            "source": self.name,
            "title": raw.get("title") or "أرض للبيع - عقار",
            "city": raw.get("city", "غير محدد"),
            "district": raw.get("district", ""),
            "area_sqm": raw.get("area_sqm", 0.0),
            "price_sar": raw.get("price", 0.0),
            "contact_phone": None,
            "image_urls": raw.get("img_src", ""),
            "source_url": f"{_BASE}{raw['href']}" if raw.get("href") else "",
            "scraped_at": datetime.now(),
        }
