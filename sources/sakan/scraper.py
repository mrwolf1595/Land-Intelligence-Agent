"""
Sakan.co Saudi Arabia scraper (sa.sakan.co).
HTML scraping — listings page. Uses multiple selector strategies because
Sakan uses CSS Modules (hashed class names that change between builds).
"""
import json
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

_BASE      = "https://sa.sakan.co"
_SEARCH    = f"{_BASE}/ar/properties/sale"
_PER_PAGE  = 21
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


def _extract_json_ld(soup) -> list[dict]:
    """Try JSON-LD structured data embedded in the page as a listing source."""
    items = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            # Could be a single item or a list
            if isinstance(data, list):
                items.extend(data)
            elif isinstance(data, dict):
                items.append(data)
        except Exception:
            continue
    return items


def _extract_next_data(soup) -> Optional[dict]:
    """Try __NEXT_DATA__ JSON if Sakan uses Next.js."""
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        return None
    try:
        return json.loads(tag.string)
    except Exception:
        return None


def _find_text_by_patterns(el, patterns: list) -> str:
    """Try multiple CSS class regex patterns to find an element text."""
    for pat in patterns:
        found = el.find(attrs={"class": re.compile(pat, re.I)})
        if found:
            return found.get_text(strip=True)
    return ""


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
                url = f"{_SEARCH}?page={page}&propertyTypes=land" if page > 1 else f"{_SEARCH}?propertyTypes=land"
                try:
                    resp = client.get(url)
                    if resp.status_code != 200:
                        logger.warning(f"[sakan] page {page}: HTTP {resp.status_code}")
                        break
                except Exception as e:
                    logger.error(f"[sakan] page {page}: {e}")
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # ── Strategy 1: __NEXT_DATA__ (fastest, most structured) ──────
                nd = _extract_next_data(soup)
                if nd:
                    listings_from_nd = self._parse_next_data(nd)
                    if listings_from_nd:
                        for item in listings_from_nd:
                            ref_id = item.get("ref_id", "")
                            lid = f"sakan_{ref_id}"
                            if ref_id in seen_refs:
                                continue
                            seen_refs.add(ref_id)
                            if listing_exists(lid):
                                consecutive_known += 1
                                continue
                            consecutive_known = 0
                            price = item.get("price", 0)
                            if price and not (PRICE_MIN <= price <= PRICE_MAX):
                                continue
                            if not _city_matches(item.get("location", "")):
                                continue
                            all_items.append(item)
                        logger.info(f"[sakan] page {page} (next-data): {len(listings_from_nd)} found")
                        if len(listings_from_nd) < _PER_PAGE:
                            break
                        time.sleep(1.0)
                        continue

                # ── Strategy 2: HTML card parsing ─────────────────────────────
                # Try multiple selectors because CSS Modules hashes class names
                cards = (
                    soup.find_all("div", class_=re.compile(r"\bcard\b", re.I)) or
                    soup.find_all("article") or
                    soup.find_all("div", attrs={"data-testid": re.compile(r"card|property|listing", re.I)})
                )

                if not cards:
                    logger.warning(f"[sakan] page {page}: no cards found — page structure may have changed")
                    logger.debug(f"[sakan] page HTML snippet: {resp.text[:500]}")
                    break

                new_on_page = 0
                for card in cards:
                    try:
                        # URL — try several link patterns
                        link = (
                            card.find("a", class_=re.compile(r"track_link|title|card", re.I)) or
                            card.find("a", href=re.compile(r"/property|/ar/"))
                        )
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
                        h2 = link.find(["h1", "h2", "h3"]) or link
                        title = h2.get_text(strip=True) if h2 else ""

                        # Price — multiple selector patterns
                        price_text = _find_text_by_patterns(card, [r"price", r"سعر", r"cost"])
                        price = _parse_price(price_text)

                        # Location
                        location = _find_text_by_patterns(card, [r"location", r"address", r"موقع", r"حي"])

                        # Area
                        area_sqm = 0.0
                        area_text = _find_text_by_patterns(card, [r"area", r"size", r"مساح"])
                        if area_text:
                            area_sqm = _parse_area(area_text)
                        # Also scan all text nodes for m² pattern
                        if not area_sqm:
                            for t in card.find_all(string=re.compile(r"م²|m²|متر")):
                                area_sqm = _parse_area(str(t))
                                if area_sqm:
                                    break

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

    def _parse_next_data(self, nd: dict) -> list[dict]:
        """Extract listings from __NEXT_DATA__ JSON (Next.js pages router)."""
        results = []
        try:
            page_props = nd.get("props", {}).get("pageProps", {})
            # Try multiple common paths
            listings = (
                page_props.get("listings") or
                page_props.get("properties") or
                page_props.get("data", {}).get("listings") or
                page_props.get("initialData", {}).get("listings") or
                []
            )
            for item in listings:
                prop = item.get("property") or item
                pid = str(prop.get("id") or prop.get("listingId") or "")
                if not pid:
                    continue
                price_obj = prop.get("price") or {}
                price = float(price_obj.get("value") or price_obj if isinstance(price_obj, (int, float)) else 0)
                loc = prop.get("location") or prop.get("address") or ""
                if isinstance(loc, dict):
                    loc = loc.get("name") or loc.get("ar") or ""
                results.append({
                    "ref_id": pid,
                    "title": prop.get("title") or "عقار للبيع",
                    "price": price,
                    "location": str(loc),
                    "area_sqm": float(prop.get("area") or prop.get("size") or 0),
                    "url": f"{_BASE}/ar/property/{pid}",
                })
        except Exception as e:
            logger.debug(f"[sakan] next-data parse error: {e}")
        return results

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
