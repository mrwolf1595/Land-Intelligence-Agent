"""
Ejar (REGA) Live Rental Data Scraper
=====================================
Source: https://ejar.rega.gov.sa  (الهيئة العامة للعقار — مؤشر إيجار)
API:    https://rentalrei.rega.gov.sa/RegaIndicatorsAPIs/api/IndicatorEjar/

Endpoints used:
  GET  /GetAllRegions               → all 13 Saudi regions with IDs
  GET  /GetCitisByRegionId?regionId → cities per region
  POST /GetDetailsV2                → avg annual rent by city + unit type

Coverage: All 13 regions, ~200+ cities, 5 unit types (شقة / فيلا / دور / استديو / دوبلاكس)
Auth:     Bearer null (public endpoint — no registration needed)
Schedule: Weekly — stores in rental_benchmarks with source='ejar'

Data quality: Based on real Ejar contracts (عقود إيجار مسجّلة).
Far superior to REGA static CSV or market estimates.
"""

import time
from datetime import datetime, date
from typing import Optional

import httpx

from core.database import get_conn
from core.logger import get_logger
from pipeline.local_data import _norm as _normalize_city

logger = get_logger("ejar")

_BASE    = "https://rentalrei.rega.gov.sa/RegaIndicatorsAPIs/api/IndicatorEjar"
_HEADERS = {
    "Content-Type":  "application/json",
    "Authorization": "Bearer null",
    "Accept":        "application/json",
    "Origin":        "https://ejar.rega.gov.sa",
    "Referer":       "https://ejar.rega.gov.sa/",
    "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# Unit type IDs confirmed from /GetAllResidentialUnitsTypes endpoint
_UNIT_TYPES: dict[str, int] = {
    "شقة":     19,
    "فيلا":    20,
    "دور":     18,
    "استديو":  25,
    "دوبلاكس": 24,
    "محل":      3,
    "مكتب":     5,
}

_RESIDENTIAL = {"شقة", "فيلا", "دور", "استديو", "دوبلاكس"}
_COMMERCIAL  = {"محل", "مكتب"}

_UNIT_AREAS: dict[str, int] = {
    "شقة":     110,
    "فيلا":    350,
    "دور":     260,
    "استديو":   45,
    "دوبلاكس": 200,
    "محل":      60,
    "مكتب":     80,
}

# Residential types only — commercial data (محل/مكتب) shows corrupted values in the API
# (e.g. 589 SAR/year for a shop is nonsensical — likely per-m² stored incorrectly)
_RELIABLE_TYPES = {"شقة", "فيلا", "دور", "استديو", "دوبلاكس"}

# Maps English unitName (from API response) → Arabic property type
# (API returns English unitName regardless of input unitTypeId)
_UNIT_NAME_AR: dict[str, str] = {
    "appartment":       "شقة",        # note: API typo (single 'p')
    "villa":            "فيلا",
    "floor":            "دور",
    "studio":           "استديو",
    "duplex":           "دوبلاكس",
    "shop":             "محل",
    "office_space":     "مكتب",
    "trade_exhibition": "معرض تجاري",
}

# Reverse map (for internal use)
_UNIT_NAME_EN: dict[str, str] = {v: k for k, v in _UNIT_NAME_AR.items()}

_MIN_DEALS = 10   # minimum contracts to trust the average


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(path: str, params: dict = None, client: httpx.Client = None) -> Optional[dict]:
    _own = client is None
    _c   = client or httpx.Client(headers=_HEADERS, timeout=20, follow_redirects=True)
    try:
        r = _c.get(f"{_BASE}/{path}", params=params)
        if r.status_code == 200:
            return r.json()
        logger.warning(f"[ejar] GET {path} → {r.status_code}")
    except Exception as e:
        logger.error(f"[ejar] GET {path} error: {e}")
    finally:
        if _own:
            _c.close()
    return None


def _post(path: str, payload: dict, client: httpx.Client, retries: int = 3) -> Optional[dict]:
    """POST with exponential backoff on 429 (rate limit)."""
    for attempt in range(retries):
        try:
            r = client.post(f"{_BASE}/{path}", json=payload)

            if r.status_code == 429:
                wait = 2 ** (attempt + 2)   # 4s, 8s, 16s
                logger.debug(f"[ejar] 429 rate-limit — waiting {wait}s (attempt {attempt+1})")
                time.sleep(wait)
                continue

            if r.status_code != 200:
                logger.warning(f"[ejar] POST {path} → {r.status_code}")
                return None

            data = r.json()
            if data.get("isSuccess") and data.get("data"):
                return data
            msgs = data.get("messages") or []
            if msgs and msgs[0]:
                logger.debug(f"[ejar] {path} msg: {msgs[0]}")
            return None

        except Exception as e:
            logger.error(f"[ejar] POST {path} error: {e}")
            if attempt < retries - 1:
                time.sleep(2)

    logger.warning(f"[ejar] POST {path} — all {retries} retries exhausted")
    return None


# ── Lookups ───────────────────────────────────────────────────────────────────

def fetch_regions(client: httpx.Client) -> list[dict]:
    data = _get("GetAllRegions", client=client)
    return (data or {}).get("data", [])


def fetch_cities(region_id: int, client: httpx.Client) -> list[dict]:
    data = _get("GetCitisByRegionId", params={"regionId": region_id}, client=client)
    return (data or {}).get("data", [])


# ── Core rental fetch ─────────────────────────────────────────────────────────

def fetch_all_city_rentals(
    city_id: int,
    region_id: int,
    year: int,
    client: httpx.Client,
) -> dict[str, dict]:
    """
    Fetch rental stats for ALL unit types in one city with a single API call.

    The API always returns all unit types in one response (unitTypeId is ignored).
    One call = data for all 8 unit types → much more efficient.

    Returns: { "شقة": {"avg_annual_rent": X, "total_deals": Y}, ... }
    """
    payload = {
        "trigger_Points":  "0",   # city-level aggregate
        "cityId":          city_id,
        "regionId":        region_id,
        "unitTypeId":      0,     # 0 = all types (API ignores this anyway)
        "rentalUnitUsage": 0,     # 0 = all usage types
        "strt_date":       f"{year}-01-01T00:00:00.000Z",
        "end_date":        f"{year}-12-31T23:59:59.000Z",
        "isQuarterly":     0,
    }

    result = _post("GetDetailsV2", payload, client)
    if not result:
        return {}

    rows = result.get("data", []) or []
    out: dict[str, dict] = {}

    for row in rows:
        unit_en   = (row.get("unitName") or "").lower()
        unit_ar   = _UNIT_NAME_AR.get(unit_en)
        deals     = int(row.get("sumDeals") or 0)
        total_rent = float(row.get("sumRent") or 0)

        if not unit_ar or deals < _MIN_DEALS or total_rent <= 0:
            continue

        out[unit_ar] = {
            "avg_annual_rent": round(total_rent / deals, 2),
            "total_deals":     deals,
        }

    return out


# Legacy single-type fetch (kept for backward compat / CLI test)
def fetch_city_rental(
    city_id: int,
    region_id: int,
    unit_type_ar: str,
    year: int,
    client: httpx.Client,
) -> Optional[dict]:
    """Fetch rental for one unit type (calls fetch_all_city_rentals internally)."""
    all_data = fetch_all_city_rentals(city_id, region_id, year, client)
    return all_data.get(unit_type_ar)


# ── Main updater ──────────────────────────────────────────────────────────────

def update_rental_benchmarks(target_year: int = None) -> int:
    """
    Fetch Ejar rental data for ALL regions/cities/unit-types and upsert
    into rental_benchmarks (source='ejar').

    • Runs in ~5-10 minutes (polite delay between requests)
    • Safe to call weekly — overwrites previous values
    • Returns number of (city, unit_type) records upserted

    Args:
        target_year: Calendar year to fetch (defaults to last full year).
    """
    if target_year is None:
        today = date.today()
        target_year = today.year if today.month > 6 else today.year - 1

    logger.info(f"[ejar] Starting rental update — year={target_year}")

    conn     = get_conn()
    now      = datetime.now().isoformat()
    upserted = 0
    skipped  = 0
    errors   = 0

    try:
        with httpx.Client(headers=_HEADERS, timeout=20, follow_redirects=True) as client:
            regions = fetch_regions(client)
            if not regions:
                logger.error("[ejar] Failed to fetch regions")
                return 0

            logger.info(f"[ejar] {len(regions)} regions, {len(_UNIT_TYPES)} unit types each")

            for region in regions:
                region_id   = region["lkRegionId"]
                region_name = region.get("lkRegionAr", "")

                cities = fetch_cities(region_id, client)
                if not cities:
                    logger.warning(f"[ejar] No cities for {region_name}")
                    continue

                city_count = len(cities)
                logger.info(f"[ejar] {region_name}: {city_count} cities")

                for city in cities:
                    city_id   = city.get("lkCityId")
                    city_name = _normalize_city(city.get("lkCityAr") or "")

                    if not city_id or not city_name or not city.get("isActive", True):
                        continue

                    # ONE API call → all unit types for this city
                    try:
                        all_data = fetch_all_city_rentals(
                            city_id, region_id, target_year, client
                        )
                    except Exception as e:
                        logger.error(f"[ejar] fetch error {city_name}: {e}")
                        errors += 1
                        continue

                    if not all_data:
                        skipped += 1
                        continue

                    for unit_type_ar, res in all_data.items():
                        # Skip commercial types — API data unreliable for shops/offices
                        if unit_type_ar not in _RELIABLE_TYPES:
                            continue
                        try:
                            area_est = _UNIT_AREAS.get(unit_type_ar, 100)
                            category = "تجاري" if unit_type_ar in _COMMERCIAL else "سكني"

                            conn.execute("""
                                INSERT INTO rental_benchmarks
                                    (city, district, property_type_ar, property_category,
                                     avg_annual_rent_sar, rent_per_sqm_year,
                                     typical_area_sqm, sample_count, source, last_updated)
                                VALUES (?, '', ?, ?, ?, ?, ?, ?, 'ejar', ?)
                                ON CONFLICT(city, district, property_type_ar) DO UPDATE SET
                                    avg_annual_rent_sar = excluded.avg_annual_rent_sar,
                                    rent_per_sqm_year   = excluded.rent_per_sqm_year,
                                    sample_count        = excluded.sample_count,
                                    source              = 'ejar',
                                    last_updated        = excluded.last_updated
                            """, (
                                city_name, unit_type_ar, category,
                                res["avg_annual_rent"],
                                round(res["avg_annual_rent"] / area_est, 2),
                                area_est,
                                res["total_deals"],
                                now,
                            ))
                            upserted += 1

                        except Exception as e:
                            logger.error(f"[ejar] DB error {city_name}/{unit_type_ar}: {e}")
                            errors += 1

                    time.sleep(1.0)    # 1s per city — ~200 cities ≈ 3-4 min total

            conn.commit()

    finally:
        conn.close()

    logger.info(
        f"[ejar] Complete — {upserted} upserted | {skipped} no-data | "
        f"{errors} errors | year={target_year}"
    )
    return upserted


# ── CLI quick test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from core.database import init_db
    init_db()

    print("=" * 60)
    print("Ejar Live Rental Test — Major Cities")
    print("=" * 60)

    with httpx.Client(headers=_HEADERS, timeout=20) as client:
        regions = fetch_regions(client)
        print(f"\n✅ {len(regions)} regions found\n")

        test_cases = [
            (1, "الرياض"),
            (2, "جدة"),
            (5, "الدمام"),
            (6, "أبها"),
        ]

        for region_id, city_filter in test_cases:
            cities = fetch_cities(region_id, client)
            city = next(
                (c for c in cities if city_filter in c.get("lkCityAr", "")), None
            )
            if not city:
                print(f"❌ {city_filter} not found")
                continue

            print(f"📍 {city['lkCityAr']} (id={city['lkCityId']}, region={region_id})")
            for unit_type in ["شقة", "فيلا", "محل"]:
                res = fetch_city_rental(city["lkCityId"], region_id, unit_type, 2024, client)
                if res:
                    print(
                        f"   {unit_type}: {res['avg_annual_rent']:>10,.0f} ر.س/سنة  "
                        f"({res['total_deals']:,} عقد)"
                    )
                else:
                    print(f"   {unit_type}: —")
            print()
