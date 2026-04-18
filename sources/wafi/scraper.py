"""
برنامج وافي (Wafi / REGA Off-Plan) Scraper
============================================
Sources:
  1. REGA Quarterly Sales Indicators CSV
     Path: Saudi-Real-Estate-Data/rega/quarter-report-SI.csv
     Fields: city_ar, district_ar, typecategoryar, deed_counts, RealEstatePrice_SUM
     Used as: "market velocity" proxy — more transactions = higher absorption = lower saturation

  2. Live: rega.gov.sa HTML scraper
     URL: /ar/rega-services/platforms/wafi-off-plan-sales-and-lease/?tabActive=Wafi+Projects&currentPage=N
     Status: Page is SSR (Umbraco CMS) — project list rendered server-side with paging
     Note: wafiservices.rega.gov.sa requires NafaZ login — not scrape-able

Architecture decision:
  • Live WAFI project portal requires auth → unavailable for scraping
  • REGA quarterly data is the best public proxy for supply/demand balance
  • We compute:
      - recent_deed_count      : transactions in last 4 quarters (demand proxy)
      - avg_price_per_sqm      : weighted avg from recent quarters
      - market_trend           : rising / stable / falling (based on QoQ change)
      - absorption_risk        : Low / Medium / High (based on deed velocity)

Absorption risk thresholds (empirical, Riyadh baseline):
  ≥ 15 deeds/quarter/district → Low     (active market)
  5–14 deeds/quarter/district → Medium
  < 5  deeds/quarter/district → High    (illiquid / oversupplied)
"""

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

import httpx

from core.logger import get_logger

logger = get_logger("wafi")

_REPO       = Path(__file__).parent.parent.parent / "Saudi-Real-Estate-Data" / "rega"
_CSV_PATH   = _REPO / "quarter-report-SI.csv"
_REGA_URL   = "https://rega.gov.sa/ar/rega-services/platforms/wafi-off-plan-sales-and-lease/"
_TIMEOUT    = 15

# Risk thresholds (quarterly deed count per district)
_RISK_HIGH   = 5
_RISK_MEDIUM = 15


# ── CSV loader ────────────────────────────────────────────────────────────────

def _load_quarterly_data() -> list[dict]:
    """
    Load REGA quarterly sales indicator CSV.
    Returns list of dicts with keys:
      year, quarter, city_ar, district_ar, type_ar, deed_counts, total_price, avg_sqm
    """
    if not _CSV_PATH.exists():
        logger.warning(f"[wafi] CSV not found: {_CSV_PATH}")
        return []
    rows = []
    try:
        with open(_CSV_PATH, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    rows.append({
                        "year":       int(row.get("yearnumber", 0) or 0),
                        "quarter":    int(row.get("quarternumber", 0) or 0),
                        "quarter_id": int(row.get("quarterid", 0) or 0),
                        "city_ar":    (row.get("city_ar") or "").strip(),
                        "district_ar":(row.get("district_ar") or "").strip(),
                        "type_ar":    (row.get("typecategoryar") or "").strip(),
                        "deeds":      int(float(row.get("deed_counts", 0) or 0)),
                        "total_price":float(row.get("RealEstatePrice_SUM", 0) or 0),
                        "avg_sqm":    float(row.get("Meter_Price_W_Avg_IQR", 0) or 0),
                    })
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        logger.error(f"[wafi] CSV load error: {e}")
    return rows


def _latest_quarters(all_rows: list[dict], n: int = 4) -> list[dict]:
    """Return rows from the most recent N quarters."""
    if not all_rows:
        return []
    quarter_ids = sorted({r["quarter_id"] for r in all_rows}, reverse=True)
    recent_ids  = set(quarter_ids[:n])
    return [r for r in all_rows if r["quarter_id"] in recent_ids]


# ── Supply pipeline analysis ──────────────────────────────────────────────────

def get_supply_pipeline(city_ar: str, district_ar: str = "") -> dict:
    """
    Analyze market velocity (transactions) as a supply-absorption proxy.

    Args:
        city_ar:     Arabic city name (e.g. "الرياض")
        district_ar: Arabic district name (optional; falls back to city-level)

    Returns:
        {
          "city":                 str,
          "district":             str,
          "recent_deed_count":    int,    # total deeds in last 4 quarters
          "deed_count_per_q":     float,  # avg deeds per quarter
          "avg_price_sqm":        float,  # weighted avg SAR/m² (last 4Q)
          "market_trend":         str,    # "rising" / "stable" / "falling"
          "absorption_risk":      str,    # "Low" / "Medium" / "High"
          "quarters_analyzed":    int,    # number of quarters found
          "source":               str,
          "is_mock":              bool,
        }
    """
    result = {
        "city":              city_ar,
        "district":          district_ar,
        "recent_deed_count": 0,
        "deed_count_per_q":  0.0,
        "avg_price_sqm":     0.0,
        "market_trend":      "unknown",
        "absorption_risk":   "Medium",
        "quarters_analyzed": 0,
        "source":            "rega_csv",
        "is_mock":           False,
    }

    all_rows = _load_quarterly_data()
    if not all_rows:
        result["is_mock"] = True
        result["source"]  = "no_data"
        return result

    # Filter to city (and optionally district)
    def _match_city(r):
        return city_ar and city_ar in r["city_ar"]

    def _match_district(r):
        return district_ar and district_ar in r["district_ar"]

    city_rows = [r for r in all_rows if _match_city(r)]
    if not city_rows:
        result["is_mock"] = True
        result["source"]  = "city_not_found"
        return result

    # Use district-level if we have enough data, else city-level
    if district_ar:
        district_rows = [r for r in city_rows if _match_district(r)]
        work_rows = district_rows if len(district_rows) >= 2 else city_rows
        result["source"] = "rega_csv_district" if len(district_rows) >= 2 else "rega_csv_city"
    else:
        work_rows = city_rows
        result["source"] = "rega_csv_city"

    # Focus on last 4 quarters of land transactions (أراضي)
    recent = _latest_quarters(work_rows, n=4)
    land_rows = [r for r in recent if "أرض" in r["type_ar"] or "أراضي" in r["type_ar"]]
    if not land_rows:
        land_rows = recent   # fall back to all types

    quarters_seen  = len({r["quarter_id"] for r in land_rows})
    total_deeds    = sum(r["deeds"] for r in land_rows)
    avg_per_q      = round(total_deeds / max(quarters_seen, 1), 1)

    # Weighted avg price/sqm (skip rows with zero)
    priced = [r for r in land_rows if r["avg_sqm"] > 0]
    if priced:
        total_w = sum(r["deeds"] * r["avg_sqm"] for r in priced)
        total_d = sum(r["deeds"] for r in priced)
        avg_sqm = round(total_w / total_d, 0) if total_d else 0.0
    else:
        avg_sqm = 0.0

    # Trend: compare first 2 vs last 2 quarters
    quarter_ids = sorted({r["quarter_id"] for r in land_rows})
    trend = "stable"
    if len(quarter_ids) >= 3:
        half   = len(quarter_ids) // 2
        early  = sum(r["deeds"] for r in land_rows if r["quarter_id"] in quarter_ids[:half])
        late   = sum(r["deeds"] for r in land_rows if r["quarter_id"] in quarter_ids[half:])
        if late > early * 1.15:
            trend = "rising"
        elif late < early * 0.85:
            trend = "falling"

    # Absorption risk
    if avg_per_q >= _RISK_MEDIUM:
        risk = "Low"
    elif avg_per_q >= _RISK_HIGH:
        risk = "Medium"
    else:
        risk = "High"

    result.update({
        "recent_deed_count":  total_deeds,
        "deed_count_per_q":   avg_per_q,
        "avg_price_sqm":      avg_sqm,
        "market_trend":       trend,
        "absorption_risk":    risk,
        "quarters_analyzed":  quarters_seen,
    })
    return result


# ── City-level summary (for market context in reports) ───────────────────────

def get_city_market_summary(city_ar: str) -> dict:
    """
    Return a ranked list of the most active districts in a city (last 4Q).
    Useful for identifying high-demand vs. oversupplied micro-markets.
    """
    all_rows = _load_quarterly_data()
    if not all_rows:
        return {"city": city_ar, "districts": [], "source": "no_data"}

    recent = _latest_quarters(all_rows, n=4)
    city_rows = [r for r in recent if city_ar in r["city_ar"]]

    # Aggregate by district
    by_district = defaultdict(lambda: {"deeds": 0, "price_weighted": 0.0, "price_total_deeds": 0})
    for r in city_rows:
        d = r["district_ar"]
        by_district[d]["deeds"] += r["deeds"]
        if r["avg_sqm"] > 0:
            by_district[d]["price_weighted"]   += r["deeds"] * r["avg_sqm"]
            by_district[d]["price_total_deeds"] += r["deeds"]

    districts = []
    for name, stats in by_district.items():
        avg_sqm = (round(stats["price_weighted"] / stats["price_total_deeds"], 0)
                   if stats["price_total_deeds"] > 0 else 0.0)
        districts.append({
            "district":    name,
            "deed_count":  stats["deeds"],
            "avg_sqm":     avg_sqm,
            "activity":    "High" if stats["deeds"] >= _RISK_MEDIUM else
                           ("Medium" if stats["deeds"] >= _RISK_HIGH else "Low"),
        })

    districts.sort(key=lambda x: x["deed_count"], reverse=True)
    return {
        "city":      city_ar,
        "districts": districts[:20],  # top 20 districts
        "source":    "rega_csv",
    }


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("WAFI Supply Pipeline — Market Velocity Analysis")
    print("=" * 60)

    test_cases = [
        ("الرياض",  "النهضة"),
        ("الرياض",  "الملقا"),
        ("جدة",     "أبحر الشمالية"),
        ("الدمام",  ""),
    ]

    for city, district in test_cases:
        d = get_supply_pipeline(city, district)
        print(f"\n📍 {city} — {district or '(كل المدينة)'}")
        print(f"   صفقات آخر 4 أرباع: {d['recent_deed_count']} ({d['deed_count_per_q']}/ربع)")
        print(f"   متوسط سعر م²:      {d['avg_price_sqm']:,.0f} ر.س")
        print(f"   اتجاه السوق:        {d['market_trend']}")
        print(f"   مخاطر التشبع:      {d['absorption_risk']}")
        print(f"   المصدر:            {d['source']}")

    print("\n" + "=" * 60)
    print("Top Districts — الرياض")
    print("=" * 60)
    summary = get_city_market_summary("الرياض")
    for dist in summary["districts"][:10]:
        print(f"  {dist['district']:<25} {dist['deed_count']:>5} صفقة  "
              f"{dist['avg_sqm']:>8,.0f} ر.س/م²  [{dist['activity']}]")
