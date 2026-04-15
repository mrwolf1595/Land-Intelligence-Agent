"""
Sakan.co Saudi Arabia scraper (sa.sakan.co).
HTML scraping — listings page + detail page.
"""
import re
import time
from datetime import datetime
from typing import Optional
import importlib

import httpx

from config import TARGET_CITIES, PRICE_MIN, PRICE_MAX
from core.logger import get_logger
from core.database import listing_exists
from sources.base import BaseSource

logger = get_logger("sakan")

_BASE = "https://sa.sakan.co"
_SEARCH = f"{_BASE}/ar/properties/sale"
_PER_PAGE = 21
_MAX_PAGES = 50

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.5",
    "Referer": "https://sa.sakan.co/ar/sale",
}

_LAND_TYPES = {"أرض", "land", "أراضي"}


def _parse_price(text: str) -> float:
    if not text:
        return 0.0
    nums = re.findall(r"[\d,]+", text.replace("\xa0", ""))
    if nums:
        return float(nums[0].replace(",", ""))
    return 0.0


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


class Scraper(BaseSource):
    name = "sakan"

    def fetch(self) -> list[dict]:
        try:
            bs4 = importlib.import_module("bs4")
            BeautifulSoup = bs4.BeautifulSoup
        except ImportError:
            logger.error("[sakan] beautifulsoup4 not installed")
            return []

        all_items = []
        seen_refs: set = set()
        consecutive_known = 0

        with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
            for page in range(1, _MAX_PAGES + 1):
                url = f"{_SEARCH}?page={page}" if page > 1 else _SEARCH
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"[sakan] page {page}: HTTP {resp.status_code}")
                        break
                except Exception as e:
                    logger.error(f"[sakan] page {page}: {e}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.find_all("div", class_=re.compile(r"card"))
                if not cards:
                    break

                new_on_page = 0
                for card in cards:
                    try:
                        # URL
                        link = card.find("a", class_=re.compile(r"track_link|card.*title|title"))
                        if not link or not link.get("href"):
                            continue
                        href = link["href"]
                        detail_url = href if href.startswith("http") else _BASE + href

                        # Ref ID from URL
                        ref_match = re.search(r"-(\d+)/?$", detail_url)
                        ref_id = ref_match.group(1) if ref_match else re.sub(r"[^a-z0-9]", "", detail_url.lower())[-12:]
                        lid = f"sakan_{ref_id}"

                        if ref_id in seen_refs:
                            continue
                        seen_refs.add(ref_id)

                        if listing_exists(lid):
                            consecutive_known += 1
                            continue
                        consecutive_known = 0

                        # Title
                        h2 = link.find("h2") or link
                        title = h2.get_text(strip=True) if h2 else ""

                        # Price
                        price_el = card.find("div", class_=re.compile(r"price"))
                        price_span = price_el.find("span") if price_el else None
                        price = _parse_price(price_span.get_text() if price_span else "")

                        # Location
                        loc_el = card.find("div", class_=re.compile(r"location"))
                        loc_span = loc_el.find("span", class_=re.compile(r"gray|fn--gray")) if loc_el else None
                        location = loc_span.get_text(strip=True) if loc_span else ""

                        # Area
                        area_sqm = 0.0
                        for amenity in card.find_all("div", class_=re.compile(r"aminit|amenity|aminities")):
                            t = amenity.get_text()
                            if "m²" in t or "م²" in t or "متر" in t:
                                area_sqm = _parse_area(t)

                        if price and not (PRICE_MIN <= price <= PRICE_MAX):
                            continue
                        if not _city_matches(location):
                            continue

                        all_items.append({
                            "ref_id": ref_id,
                            "title": title,
                            "price": price,
                            "location": location,
                            "area_sqm": area_sqm,
                            "url": detail_url,
                        })
                        new_on_page += 1

                    except Exception as e:
                        logger.debug(f"[sakan] card parse error: {e}")
                        continue

                logger.info(f"[sakan] page {page}: {new_on_page} new listings")

                if consecutive_known >= 10:
                    logger.info("[sakan] early stop (10 consecutive known)")
                    break

                if len(cards) < _PER_PAGE:
                    break  # last page

                time.sleep(1.5)

        logger.info(f"[sakan] done — {len(all_items)} new listings")
        return all_items

    def normalize(self, raw: dict) -> dict:
        location = raw.get("location", "")
        city = "غير محدد"
        district = ""
        if "،" in location:
            parts = [p.strip() for p in location.split("،")]
            city = parts[-1] if parts else location
            district = parts[0] if len(parts) > 1 else ""
        elif location:
            city = location

        return {
            "listing_id": f"sakan_{raw['ref_id']}",
            "source": self.name,
            "title": raw.get("title", "عقار للبيع"),
            "city": city,
            "district": district,
            "area_sqm": raw.get("area_sqm", 0.0),
            "price_sar": raw.get("price", 0.0),
            "contact_phone": None,
            "contact_name": None,
            "image_urls": "",
            "source_url": raw.get("url", ""),
            "scraped_at": datetime.now(),
        }
