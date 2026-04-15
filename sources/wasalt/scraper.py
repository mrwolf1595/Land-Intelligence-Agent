"""
Wasalt.sa real estate scraper.

Strategy:
1. Try HTTP scraping: GET /sale/search?page=N, extract __NEXT_DATA__ JSON embedded in HTML.
   Filter for land sub-types (أرض / أرض متعددة الاستخدام / أرض تجارية).
   Stop early when 15+ consecutive listings already exist in DB.
2. If HTTP returns 403 (bot-blocked): fall back to existing SQLite adapter.
"""
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from config import TARGET_CITIES, PRICE_MIN, PRICE_MAX, WASALT_DB_PATH
from core.logger import get_logger
from core.database import listing_exists
from sources.base import BaseSource

logger = get_logger("wasalt")

_BASE       = "https://wasalt.sa"
_SEARCH_URL = f"{_BASE}/sale/search"
_MAX_PAGES  = 15
_EARLY_STOP = 15   # stop after N consecutive known listings

_HEADERS = {
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ar,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "User-Agent":      (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer":          "https://wasalt.sa/",
    "Sec-Fetch-Dest":   "document",
    "Sec-Fetch-Mode":   "navigate",
    "Sec-Fetch-Site":   "same-origin",
    "Cache-Control":    "no-cache",
}

_LAND_TYPES = {"أرض", "أرض متعددة الاستخدام", "أرض تجارية"}

_CITY_ALIASES: dict[str, list[str]] = {
    "الرياض":       ["الرياض", "riyadh"],
    "جدة":          ["جدة", "جده", "jeddah"],
    "مكة":          ["مكة", "مكه", "مكة المكرمة", "makkah", "mecca"],
    "المدينة":      ["المدينة", "المدينة المنورة", "madinah", "medina"],
    "الدمام":       ["الدمام", "dammam"],
    "الخبر":        ["الخبر", "khobar"],
    "القصيم":       ["القصيم", "بريدة", "qassim"],
    "تبوك":         ["تبوك", "tabuk"],
    "حائل":         ["حائل", "hail"],
    "الأحساء":      ["الأحساء", "ahsa", "al ahsa"],
    "أبها":         ["أبها", "abha"],
    "خميس مشيط":   ["خميس مشيط", "khamis mushait"],
}


def _extract_next_data(html: str) -> Optional[dict]:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.+?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def _city_matches(city: str) -> bool:
    if not city:
        return False
    city_lower = city.lower().strip()
    for aliases in _CITY_ALIASES.values():
        if any(a.lower() in city_lower or city_lower in a.lower() for a in aliases):
            return True
    return False


def _normalize_city(city: str) -> str:
    if not city:
        return "غير محدد"
    city_lower = city.lower().strip()
    for canonical, aliases in _CITY_ALIASES.items():
        if any(a.lower() in city_lower or city_lower in a.lower() for a in aliases):
            return canonical
    return city


class Scraper(BaseSource):
    name = "wasalt"

    def fetch(self) -> list[dict]:
        items = self._fetch_web()
        if items is not None:          # None = blocked; [] = ran but found nothing new
            return items
        # httpx blocked — try Selenium
        items = self._fetch_selenium()
        if items is not None:
            return items
        # Selenium not available — SQLite fallback
        logger.warning("[wasalt] All web methods failed — falling back to SQLite")
        return self._fetch_sqlite()

    # ── Web scraper ────────────────────────────────────────────────────────────

    def _fetch_web(self) -> Optional[list[dict]]:
        """Returns list of raw property dicts, or None if HTTP blocked."""
        all_items: list[dict] = []
        seen_ids:  set[str]   = set()
        consecutive_known = 0

        with httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True) as client:
            for page in range(_MAX_PAGES):
                url = f"{_SEARCH_URL}?page={page}"
                try:
                    resp = client.get(url)
                except Exception as exc:
                    logger.error(f"[wasalt] page {page} request error: {exc}")
                    break

                if resp.status_code == 403:
                    logger.warning(f"[wasalt] HTTP 403 on page {page}")
                    return None   # Signal "blocked"

                if resp.status_code != 200:
                    logger.warning(f"[wasalt] page {page}: HTTP {resp.status_code}")
                    break

                nd = _extract_next_data(resp.text)
                if not nd:
                    logger.warning(f"[wasalt] page {page}: __NEXT_DATA__ not found")
                    break

                props = (
                    nd.get("props", {})
                      .get("pageProps", {})
                      .get("searchResult", {})
                      .get("properties", [])
                )
                if not props:
                    break

                new_on_page = 0
                for prop in props:
                    info = prop.get("propertyInfo") or {}
                    sub_type = info.get("propertySubType", "")
                    if sub_type not in _LAND_TYPES:
                        continue

                    eid = str(prop.get("id", ""))
                    if not eid or eid in seen_ids:
                        continue
                    seen_ids.add(eid)

                    lid = f"wasalt_{eid}"
                    if listing_exists(lid):
                        consecutive_known += 1
                        continue

                    consecutive_known = 0

                    price = float(info.get("salePrice") or info.get("conversionPrice") or 0)
                    if price and not (PRICE_MIN <= price <= PRICE_MAX):
                        continue

                    city = info.get("city", "")
                    if TARGET_CITIES and not _city_matches(city):
                        continue

                    all_items.append(prop)
                    new_on_page += 1

                logger.info(f"[wasalt] page {page}: {new_on_page} new land listings")

                if consecutive_known >= _EARLY_STOP:
                    logger.info(f"[wasalt] {_EARLY_STOP} consecutive known — stopping early")
                    break

                time.sleep(1.0)

        logger.info(f"[wasalt] web done — {len(all_items)} new listings")
        return all_items

    # ── Selenium fallback ─────────────────────────────────────────────────────

    def _fetch_selenium(self) -> Optional[list[dict]]:
        """Try Selenium-based scraping (Kali Linux with geckodriver)."""
        try:
            from selenium import webdriver
            from selenium.webdriver.firefox.service import Service
            from selenium.webdriver.firefox.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from bs4 import BeautifulSoup as BS
        except ImportError:
            logger.info("[wasalt] Selenium not available")
            return None

        GECKO = "/usr/local/bin/geckodriver"
        if not os.path.exists(GECKO):
            logger.info(f"[wasalt] geckodriver not found at {GECKO}")
            return None

        logger.info("[wasalt] Trying Selenium scraper...")
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.set_preference("permissions.default.image", 2)  # disable images

        try:
            driver = webdriver.Firefox(service=Service(GECKO), options=options)
        except Exception as e:
            logger.error(f"[wasalt] Firefox launch failed: {e}")
            return None

        all_items = []
        seen_ids: set = set()
        consecutive_known = 0

        try:
            for page in range(_MAX_PAGES):
                url = f"{_SEARCH_URL}?propertyFor=sale&countryId=1&type=residential&page={page}"
                try:
                    driver.get(url)
                    WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.ID, "__NEXT_DATA__"))
                    )
                    soup = BS(driver.page_source, "html.parser")
                    script = soup.find("script", id="__NEXT_DATA__")
                    if not script:
                        break
                    nd = json.loads(script.string)
                except Exception as e:
                    logger.error(f"[wasalt] Selenium page {page} error: {e}")
                    break

                props = nd.get("props", {}).get("pageProps", {}).get("searchResult", {}).get("properties", [])
                if not props:
                    break

                new_on_page = 0
                for prop in props:
                    info = prop.get("propertyInfo") or {}
                    if info.get("propertySubType") not in _LAND_TYPES:
                        continue
                    eid = str(prop.get("id", ""))
                    if not eid or eid in seen_ids:
                        continue
                    seen_ids.add(eid)
                    lid = f"wasalt_{eid}"
                    if listing_exists(lid):
                        consecutive_known += 1
                        continue
                    consecutive_known = 0
                    price = float(info.get("salePrice") or info.get("conversionPrice") or 0)
                    if price and not (PRICE_MIN <= price <= PRICE_MAX):
                        continue
                    city = info.get("city", "")
                    if TARGET_CITIES and not _city_matches(city):
                        continue
                    all_items.append(prop)
                    new_on_page += 1

                logger.info(f"[wasalt] Selenium page {page}: {new_on_page} new")
                if consecutive_known >= _EARLY_STOP:
                    logger.info("[wasalt] Early stop (consecutive known)")
                    break
                time.sleep(2.0)
        finally:
            driver.quit()

        logger.info(f"[wasalt] Selenium done — {len(all_items)} new listings")
        return all_items

    # ── SQLite fallback ────────────────────────────────────────────────────────

    def _fetch_sqlite(self) -> list[dict]:
        import sqlite3
        db_path = Path(WASALT_DB_PATH) if WASALT_DB_PATH else None
        if not db_path or not db_path.exists():
            logger.info(f"[wasalt] SQLite DB not found at {WASALT_DB_PATH!r}")
            return []
        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute("SELECT * FROM listings ORDER BY ROWID DESC LIMIT 50")
            cols = [d[0] for d in cursor.description]
            rows = [{"_sqlite": True, **dict(zip(cols, r))} for r in cursor.fetchall()]
            conn.close()
            logger.info(f"[wasalt] SQLite returned {len(rows)} rows")
            return rows
        except Exception as e:
            logger.error(f"[wasalt] SQLite error: {e}")
            return []

    # ── Normalization ──────────────────────────────────────────────────────────

    def normalize(self, raw: dict) -> dict:
        if raw.get("_sqlite"):
            return {
                "listing_id":    f"wasalt_{raw.get('id') or uuid.uuid4().hex[:8]}",
                "source":        self.name,
                "title":         str(raw.get("title", "أرض للبيع")),
                "city":          _normalize_city(raw.get("city", "")),
                "district":      raw.get("district", ""),
                "area_sqm":      float(raw.get("area_size") or raw.get("area") or 0),
                "price_sar":     float(raw.get("price", 0)),
                "contact_phone": raw.get("phone") or raw.get("contact"),
                "image_urls":    raw.get("image_urls") or raw.get("images", ""),
                "source_url":    raw.get("url") or raw.get("link", _BASE),
                "scraped_at":    datetime.now(),
            }

        # Web scraper path
        info     = raw.get("propertyInfo") or {}
        prop_id  = str(raw.get("id", ""))
        slug     = info.get("slug", "")
        url      = f"{_BASE}/property/sale/{slug}" if slug else f"{_BASE}/property/{prop_id}"

        return {
            "listing_id":    f"wasalt_{prop_id}",
            "source":        self.name,
            "title":         info.get("title", "أرض للبيع"),
            "city":          _normalize_city(info.get("city", "")),
            "district":      info.get("zone") or info.get("territory", ""),
            "area_sqm":      float(raw.get("floorSize") or 0),
            "price_sar":     float(info.get("salePrice") or info.get("conversionPrice") or 0),
            "contact_phone": None,
            "image_urls":    "",
            "source_url":    url,
            "scraped_at":    datetime.now(),
        }
