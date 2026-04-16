"""
Wasalt.sa real estate scraper.

Strategy:
1. curl_cffi with Chrome TLS impersonation — bypasses Cloudflare JS challenge.
   Fetches /sale/search pages, extracts __NEXT_DATA__ JSON.
   Filter for land sub-types (أرض / أرض متعددة الاستخدام / أرض تجارية).
2. httpx fallback if curl_cffi not installed.
3. Selenium fallback if both HTTP methods fail.
4. Legacy SQLite fallback as last resort.
"""
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import curl_cffi.requests as _cffi_req
    _HAS_CFFI = True
except ImportError:
    _HAS_CFFI = False
    import httpx

from config import TARGET_CITIES, PRICE_MIN, PRICE_MAX, WASALT_DB_PATH
from core.logger import get_logger
from core.database import listing_exists
from sources.base import BaseSource

logger = get_logger("wasalt")

_BASE       = "https://wasalt.sa"
_EARLY_STOP = 15   # stop after N consecutive known listings

# URL patterns to try in order (most reliable first)
_SEARCH_URLS = [
    f"{_BASE}/sale/search",                            # ✅ confirmed working with curl_cffi
    f"{_BASE}/sale/search?type=residential&subType=land",
    f"{_BASE}/sa-ar/properties-for-sale",
    f"{_BASE}/sa-en/residential-lands-for-sale",
]

_MAX_PAGES = 15

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

_LAND_TYPES = {"أرض", "أرض متعددة الاستخدام", "أرض تجارية", "land", "residential-land"}

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


def _extract_properties_from_nd(nd: dict) -> list[dict]:
    """
    Try multiple known JSON paths inside __NEXT_DATA__ to find property lists.
    Wasalt has changed this path between redesigns.
    """
    page_props = nd.get("props", {}).get("pageProps", {})

    # Known paths tried in order
    candidates = [
        page_props.get("searchResult", {}).get("properties"),
        page_props.get("data", {}).get("properties"),
        page_props.get("properties"),
        page_props.get("listings"),
        page_props.get("initialData", {}).get("properties"),
    ]
    for c in candidates:
        if isinstance(c, list) and c:
            return c

    # Recursive search for a key named "properties" or "listings" that's a list
    def _find_list(obj, depth=0):
        if depth > 5 or not isinstance(obj, dict):
            return None
        for key in ("properties", "listings", "items", "data"):
            v = obj.get(key)
            if isinstance(v, list) and v:
                return v
        for v in obj.values():
            if isinstance(v, dict):
                found = _find_list(v, depth + 1)
                if found:
                    return found
        return None

    return _find_list(page_props) or []


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
        """
        Try each search URL pattern in order.
        Uses curl_cffi (Chrome TLS impersonation) to bypass Cloudflare.
        Falls back to httpx if curl_cffi is unavailable.
        Returns list of raw property dicts, or None if all URLs fail.
        """
        if _HAS_CFFI:
            logger.info("[wasalt] Using curl_cffi (Chrome impersonation) to bypass Cloudflare")
            session = _cffi_req.Session()
            get_fn = lambda url: session.get(url, impersonate="chrome110", timeout=30)
        else:
            logger.warning("[wasalt] curl_cffi not available — falling back to httpx (may be blocked)")
            _client = httpx.Client(headers=_HEADERS, timeout=30, follow_redirects=True)
            get_fn = lambda url: _client.get(url)

        try:
            for base_url in _SEARCH_URLS:
                result = self._try_url_pattern(get_fn, base_url)
                if result is not None:
                    return result
                logger.info(f"[wasalt] URL pattern {base_url!r} failed — trying next")
        finally:
            if _HAS_CFFI:
                session.close()
            else:
                _client.close()

        logger.warning("[wasalt] All HTTP URL patterns failed")
        return None

    def _try_url_pattern(self, get_fn, base_url: str) -> Optional[list[dict]]:
        """
        Paginate through a URL pattern.
        get_fn: callable(url) -> response object
        Returns list (possibly empty) on success, None if blocked/failed.
        """
        all_items: list[dict] = []
        seen_ids:  set[str]   = set()
        consecutive_known = 0

        for page in range(_MAX_PAGES):
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}page={page}"
            try:
                resp = get_fn(url)
            except Exception as exc:
                logger.error(f"[wasalt] {url} request error: {exc}")
                return None if page == 0 else all_items

            if resp.status_code == 403:
                logger.warning(f"[wasalt] HTTP 403 on {url} (bot-blocked)")
                return None

            if resp.status_code != 200:
                if page == 0:
                    logger.warning(f"[wasalt] HTTP {resp.status_code} on {url}")
                    return None
                break

            nd = _extract_next_data(resp.text)
            if not nd:
                if page == 0:
                    logger.info(f"[wasalt] No __NEXT_DATA__ at {url}")
                    return None
                break

            props = _extract_properties_from_nd(nd)
            if not props:
                if page == 0:
                    logger.info(f"[wasalt] __NEXT_DATA__ found but no properties list at {url}")
                    return None
                break

            new_on_page = 0
            for prop in props:
                if not isinstance(prop, dict):
                    continue
                # Accept both nested (propertyInfo) and flat formats
                info = prop.get("propertyInfo") or prop
                if not isinstance(info, dict):
                    info = prop
                sub_type = (
                    info.get("propertySubType") or
                    info.get("subType") or
                    info.get("type") or
                    ""
                )
                # Accept if sub_type matches or is empty (try to grab land via price/area filter)
                if sub_type and not any(lt.lower() in sub_type.lower() for lt in _LAND_TYPES):
                    continue

                eid = str(prop.get("id") or info.get("id") or "")
                if not eid or eid in seen_ids:
                    continue
                seen_ids.add(eid)

                lid = f"wasalt_{eid}"
                if listing_exists(lid):
                    consecutive_known += 1
                    continue

                consecutive_known = 0

                price = float(
                    info.get("salePrice") or info.get("price") or
                    info.get("conversionPrice") or prop.get("price") or 0
                )
                if price and not (PRICE_MIN <= price <= PRICE_MAX):
                    continue

                city = info.get("city") or info.get("cityName") or prop.get("city") or ""
                if TARGET_CITIES and not _city_matches(city):
                    continue

                all_items.append(prop)
                new_on_page += 1

            logger.info(f"[wasalt] {base_url} page {page}: {new_on_page} new land listings")

            if consecutive_known >= _EARLY_STOP:
                logger.info(f"[wasalt] {_EARLY_STOP} consecutive known — stopping early")
                break

            time.sleep(1.0)

        logger.info(f"[wasalt] {base_url}: {len(all_items)} new listings collected")
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
        search_url = f"{_BASE}/sa-en/residential-lands-for-sale"

        try:
            for page in range(_MAX_PAGES):
                url = f"{search_url}?page={page}"
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

                props = _extract_properties_from_nd(nd)
                if not props:
                    break

                new_on_page = 0
                for prop in props:
                    if not isinstance(prop, dict):
                        continue
                    info = prop.get("propertyInfo") or prop
                    if not isinstance(info, dict):
                        info = prop
                    sub_type = info.get("propertySubType") or info.get("subType") or ""
                    if sub_type and not any(lt.lower() in sub_type.lower() for lt in _LAND_TYPES):
                        continue
                    eid = str(prop.get("id") or "")
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

        # Web scraper path — support both nested (propertyInfo) and flat layouts
        info    = raw.get("propertyInfo") or raw
        prop_id = str(raw.get("id") or info.get("id") or "")
        slug    = info.get("slug", "")
        url     = f"{_BASE}/property/sale/{slug}" if slug else f"{_BASE}/property/{prop_id}"

        city_raw = info.get("city") or info.get("cityName") or raw.get("city") or ""

        return {
            "listing_id":    f"wasalt_{prop_id}",
            "source":        self.name,
            "title":         info.get("title") or raw.get("title") or "أرض للبيع",
            "city":          _normalize_city(city_raw),
            "district":      info.get("zone") or info.get("territory") or info.get("district") or "",
            "area_sqm":      float(raw.get("floorSize") or info.get("area") or 0),
            "price_sar":     float(
                info.get("salePrice") or info.get("price") or
                info.get("conversionPrice") or raw.get("price") or 0
            ),
            "contact_phone": info.get("phone") or raw.get("phone"),
            "image_urls":    "",
            "source_url":    url,
            "scraped_at":    datetime.now(),
        }
