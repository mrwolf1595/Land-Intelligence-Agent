"""
Saudi Ministry of Justice — Real Estate Exchange Scraper
سكريبر البورصة العقارية للمحكمة العليا

Source: https://srem.moj.gov.sa/
API:    https://prod-srem-api-srem.moj.gov.sa/api/v1/Dashboard/

Confirmed-working endpoints (discovered via browser network inspection 2026-04-18):

  GET  /GetMarketIndex
       → { Index: float, Change: float }

  POST /GetTrendingDistricts
       Body: { "PeriodCategory": "<char>" }
       PeriodCategory values: H=hour, D=day, W=week, M=month, Y=year, A=all-time
       → { TrendingDistricts: [ { DistrictCode, DistrictName, CityCode, CityName,
                                   RegionCode, RegionName,
                                   TotalCount, TotalPrice, TotalArea } ] }
       NOTE: Always returns top-5 per period. Call all periods to maximise coverage.
       avg_price_per_sqm = TotalPrice / TotalArea  (real closed transactions)

Key insight: price_benchmarks built from scraping ask-prices; MOJ gives closed-deal prices.
We store MOJ data in market_reference_prices (independent table) and blend it in benchmarks.py.
"""

import httpx
from datetime import datetime
from core.logger import get_logger

logger = get_logger("moj")

_BASE    = "https://prod-srem-api-srem.moj.gov.sa/api/v1/Dashboard"
_HEADERS = {
    "Content-Type":  "application/json",
    "Accept":        "application/json, text/plain, */*",
    "Origin":        "https://srem.moj.gov.sa",
    "Referer":       "https://srem.moj.gov.sa/",
    "User-Agent":    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

# All period chars that return unique top-5 districts
# Y and A give the most stable long-term benchmarks; M/W give recent signals
_PERIODS = ["Y", "A", "M", "W", "D"]


# ── Public API ────────────────────────────────────────────────────────────────

def get_market_index() -> dict:
    """Return the overall MOJ Real Estate Exchange Index.

    Returns: { "index": float, "change_pct": float } or {}
    """
    try:
        r = httpx.get(f"{_BASE}/GetMarketIndex", headers=_HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        if data.get("IsSuccess") and data.get("Data"):
            d = data["Data"]
            return {
                "index":      float(d.get("Index", 0)),
                "change_pct": float(d.get("Change", 0)),
            }
        logger.warning(f"GetMarketIndex returned non-success: {data.get('ErrorList')}")
        return {}
    except Exception as e:
        logger.error(f"GetMarketIndex error: {e}")
        return {}


def get_trending_districts(period: str = "M") -> list[dict]:
    """Fetch top-5 most-traded districts for a given period.

    Args:
        period: One of H/D/W/M/Y/A

    Returns list of dicts:
        {
          city, district, city_code, district_code, region,
          transactions, total_price_sar, total_area_sqm,
          avg_price_per_sqm, period
        }
    """
    try:
        r = httpx.post(
            f"{_BASE}/GetTrendingDistricts",
            headers=_HEADERS,
            json={"PeriodCategory": period},    # ← must be uppercase P, Char type
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("IsSuccess"):
            logger.warning(f"GetTrendingDistricts[{period}] failed: {data.get('ErrorList')}")
            return []

        raw = data.get("Data", {}).get("TrendingDistricts", [])
        results = []
        for d in raw:
            total_area  = float(d.get("TotalArea",  0))
            total_price = float(d.get("TotalPrice", 0))
            count       = int(d.get("TotalCount",   0))
            if total_area <= 0 or count < 2:
                continue
            results.append({
                "city":             d.get("CityName",     "").strip(),
                "district":         d.get("DistrictName", "").strip(),
                "city_code":        d.get("CityCode"),
                "district_code":    d.get("DistrictCode"),
                "region":           d.get("RegionName",   "").strip(),
                "transactions":     count,
                "total_price_sar":  total_price,
                "total_area_sqm":   total_area,
                "avg_price_per_sqm": round(total_price / total_area, 2),
                "period":           period,
            })
        return results

    except Exception as e:
        logger.error(f"GetTrendingDistricts[{period}] error: {e}")
        return []


def fetch_all_districts() -> list[dict]:
    """Collect unique districts across all periods to maximise coverage.

    Each period returns top-5 — by sweeping all periods we get ~20-30 unique districts.
    For duplicates (same district in multiple periods), keeps the record with most transactions.

    Returns list of enriched district dicts.
    """
    seen: dict[int, dict] = {}   # district_code → best record

    for period in _PERIODS:
        records = get_trending_districts(period)
        logger.debug(f"MOJ period={period}: {len(records)} districts")
        for rec in records:
            code = rec.get("district_code")
            if code is None:
                continue
            # Keep the record with the largest sample (most transactions = most reliable)
            existing = seen.get(code)
            if existing is None or rec["transactions"] > existing["transactions"]:
                seen[code] = rec

    all_districts = list(seen.values())
    logger.info(f"MOJ: collected {len(all_districts)} unique districts across {len(_PERIODS)} periods")
    return all_districts


# ── Database integration ───────────────────────────────────────────────────────

def update_reference_prices(conn=None) -> int:
    """Fetch MOJ data and upsert into market_reference_prices table.

    This is the ONLY function main.py / benchmarks.py needs to call.
    Returns number of districts updated.
    """
    from core.database import get_conn
    if conn is None:
        conn = get_conn()

    districts = fetch_all_districts()
    if not districts:
        logger.warning("MOJ: no districts fetched — skipping update")
        return 0

    now = datetime.now().isoformat()
    updated = 0
    for d in districts:
        if not d["city"] or not d["district"]:
            continue
        try:
            conn.execute("""
                INSERT INTO market_reference_prices
                    (city, district, price_per_sqm, source, transaction_date, sample_count, created_at)
                VALUES (?, ?, ?, 'moj', ?, ?, ?)
                ON CONFLICT(city, district, source) DO UPDATE SET
                    price_per_sqm      = excluded.price_per_sqm,
                    transaction_date   = excluded.transaction_date,
                    sample_count       = excluded.sample_count,
                    created_at         = excluded.created_at
            """, (
                d["city"],
                d["district"],
                d["avg_price_per_sqm"],
                now[:10],           # date only
                d["transactions"],
                now,
            ))
            updated += 1
        except Exception as e:
            logger.error(f"MOJ DB write error for {d['city']}/{d['district']}: {e}")

    conn.commit()
    logger.info(f"MOJ: upserted {updated} reference prices into market_reference_prices")
    return updated


# ── CLI test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("MOJ Real Estate Exchange — Live Test")
    print("=" * 60)

    idx = get_market_index()
    print(f"\n📊 Market Index: {idx.get('index', 'N/A'):,.2f}  |  Change: {idx.get('change_pct', 0):+.2f}%")

    print(f"\n🏙️  Fetching districts across all periods ({_PERIODS})...")
    districts = fetch_all_districts()
    print(f"   Total unique districts: {len(districts)}")

    print("\nTop 10 by avg price/m²:")
    for d in sorted(districts, key=lambda x: x["avg_price_per_sqm"], reverse=True)[:10]:
        print(
            f"  {d['city']:12s} | {d['district']:15s} | "
            f"{d['avg_price_per_sqm']:,.0f} ر.س/م²  | "
            f"{d['transactions']:,} صفقة"
        )
