"""
البنك المركزي السعودي (SAMA) Scraper
======================================
Sources (priority order):
  1. Live: SAMA Open Data API  → https://data.gov.sa / SAMA stats page
  2. CSV:  Saudi-Real-Estate-Data/sama/  (updated weekly via git pull)
     • SAMA-Table-8_1.csv   → CPI / inflation (Housing index column)
     • SAMA-Table-12e.csv   → Real estate loans total (market health)
     • SAMA-Table-12f.csv   → New residential mortgages (individual banks)
     • SAMA-Table-2_7.csv   → New residential mortgages (finance companies)

SAIBOR:
  SAMA publishes SAIBOR on: https://www.sama.gov.sa/en-US/EconomicReports/Pages/MonthlyStatistics.aspx
  We scrape it live and fall back to last known value from Table-12e context.

Used by:
  pipeline/financial.py → calculate_roi() for WACC / financing cost
  pipeline/analyzer.py  → market health context
"""

import csv
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import httpx

from core.logger import get_logger

logger = get_logger("sama")

_REPO     = Path(__file__).parent.parent.parent / "Saudi-Real-Estate-Data" / "sama"
_TIMEOUT  = 10

# ── Fallback values (updated manually when SAMA changes rates) ────────────────
# SAIBOR 3M: ~5.27% as of Q1 2025 (following Fed cuts from 5.6% peak)
# SAIBOR 6M: ~5.35% as of Q1 2025
_FALLBACK = {
    "saibor_3m_pct":   5.27,
    "saibor_6m_pct":   5.35,
    "repo_rate_pct":   5.00,    # SAMA repo rate
    "inflation_pct":   1.90,    # CPI YoY ~1.9% (housing sector slightly higher ~2.1%)
    "housing_cpi_pct": 2.10,
    "mortgage_growth_pct": 8.5, # YoY growth in residential mortgages
    "source":          "fallback",
    "as_of":           "2025-Q1",
}


# ── SAMA live scraper ─────────────────────────────────────────────────────────

def _fetch_saibor_live() -> Optional[dict]:
    """
    Try to fetch current SAIBOR from SAMA's publicly accessible stats page.
    Returns dict with saibor_3m_pct / saibor_6m_pct or None on failure.
    """
    try:
        # SAMA's key rates JSON (undocumented but stable since 2021)
        url = "https://www.sama.gov.sa/en-US/_layouts/15/SAMA.Statistic.WebParts/SamaWebServiceProxy.aspx"
        params = {"ReportName": "KeyRates", "ReportType": "JSON", "Language": "EN"}
        r = httpx.get(url, params=params, timeout=_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            # Response: { "SAIBOR3M": "5.27", "SAIBOR6M": "5.35", "RepoRate": "5.00", ... }
            rates = {}
            raw = data if isinstance(data, dict) else {}
            for k, v in raw.items():
                try:
                    rates[k.lower()] = float(str(v).replace("%", "").strip())
                except (ValueError, TypeError):
                    pass
            if rates:
                return {
                    "saibor_3m_pct":  rates.get("saibor3m", rates.get("saibor_3m")),
                    "saibor_6m_pct":  rates.get("saibor6m", rates.get("saibor_6m")),
                    "repo_rate_pct":  rates.get("reporate", rates.get("repo_rate")),
                    "source":         "sama_live",
                }
    except Exception as e:
        logger.debug(f"[sama] live fetch failed: {e}")
    return None


# ── CSV parsers ───────────────────────────────────────────────────────────────

def _parse_table_8_1() -> Optional[dict]:
    """
    Parse SAMA-Table-8_1.csv (CPI by expenditure division).
    Returns latest annual YoY change for:
      - General CPI index
      - Housing / Water / Electricity / Gas column (col index 5)
    """
    path = _REPO / "SAMA-Table-8_1.csv"
    if not path.exists():
        return None
    try:
        rows = []
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for _ in range(8):   # skip 8 header rows
                next(reader, None)
            for row in reader:
                if not row or not row[0]:
                    continue
                rows.append(row)

        # Find annual rows (no quarter prefix — col[1] is the year number or empty)
        annual = [r for r in rows if r[0] and not r[0].startswith("Q") and len(r) > 5]
        if len(annual) < 2:
            return None

        def _val(row, col):
            try:
                return float(row[col].replace(",", "").strip())
            except (ValueError, IndexError):
                return None

        latest   = annual[-1]
        previous = annual[-2]

        gen_now  = _val(latest, 2)
        gen_prev = _val(previous, 2)
        hou_now  = _val(latest, 5)
        hou_prev = _val(previous, 5)

        gen_yoy = round((gen_now - gen_prev) / gen_prev * 100, 2) if gen_now and gen_prev else None
        hou_yoy = round((hou_now - hou_prev) / hou_prev * 100, 2) if hou_now and hou_prev else None

        return {
            "inflation_pct":   gen_yoy,
            "housing_cpi_pct": hou_yoy,
            "cpi_base_year":   2023,
        }
    except Exception as e:
        logger.warning(f"[sama] Table-8_1 parse error: {e}")
        return None


def _parse_table_12e() -> Optional[dict]:
    """
    Parse SAMA-Table-12e.csv (Real Estate Loans by Banks).
    Returns latest total loan balance and YoY growth %.
    """
    path = _REPO / "SAMA-Table-12e.csv"
    if not path.exists():
        return None
    try:
        annual_rows = []
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for _ in range(5):
                next(reader, None)
            for row in reader:
                if not row or not row[0]:
                    continue
                # Annual rows: first col is a 4-digit year or Excel serial date
                if row[0].startswith("Q"):
                    continue
                try:
                    yr = int(float(row[0]))
                    # Detect Excel serial: values > 10000 are serial dates, < 2050 are years
                    if yr > 10000:
                        continue    # serial date row — skip
                    annual_rows.append((yr, row))
                except (ValueError, TypeError):
                    continue

        if len(annual_rows) < 2:
            return None

        # Sort by year
        annual_rows.sort(key=lambda x: x[0])
        _, latest   = annual_rows[-1]
        _, previous = annual_rows[-2]

        def _f(row, col):
            try: return float(row[col].replace(",", "").strip())
            except: return None

        total_now  = _f(latest,   4)     # Total column
        total_prev = _f(previous, 4)

        growth_pct = round((total_now - total_prev) / total_prev * 100, 1) if total_now and total_prev else None

        return {
            "re_loans_total_bn_sar":  round(total_now / 1000, 1) if total_now else None,
            "re_loans_yoy_pct":       growth_pct,
            "re_loans_retail_bn_sar": round(_f(latest, 2) / 1000, 1) if _f(latest, 2) else None,
        }
    except Exception as e:
        logger.warning(f"[sama] Table-12e parse error: {e}")
        return None


def _parse_mortgage_volumes() -> Optional[dict]:
    """
    Parse SAMA-Table-12f.csv (New Mortgages — Banks) for latest quarter contract count.
    Used as a market liquidity signal: rising mortgages = healthy demand.
    """
    path = _REPO / "SAMA-Table-12f.csv"
    if not path.exists():
        return None
    try:
        rows = []
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            for _ in range(5):
                next(reader, None)
            for row in reader:
                if row and row[0]:
                    rows.append(row)

        # Only quarterly rows (Q1..Q4)
        quarterly = [r for r in rows if r[0].startswith("Q")]
        if not quarterly:
            return None

        latest = quarterly[-1]
        def _i(row, col):
            try: return int(float(row[col].replace(",", "")))
            except: return None
        def _f(row, col):
            try: return float(row[col].replace(",", ""))
            except: return None

        contracts = _i(latest, 2)
        volume_mn = _f(latest, 6)

        # YoY: compare to same quarter last year (4 rows back)
        yoy_pct = None
        if len(quarterly) >= 5:
            prev_year = quarterly[-5]
            prev_v = _f(prev_year, 6)
            if prev_v and volume_mn:
                yoy_pct = round((volume_mn - prev_v) / prev_v * 100, 1)

        return {
            "new_mortgages_contracts_latest_q": contracts,
            "new_mortgages_volume_mn_sar":       round(volume_mn / 1000, 1) if volume_mn else None,
            "mortgage_growth_pct":               yoy_pct,
        }
    except Exception as e:
        logger.warning(f"[sama] Table-12f parse error: {e}")
        return None


# ── Main entry point ──────────────────────────────────────────────────────────

def get_financing_rates() -> dict:
    """
    Return SAIBOR, inflation, and mortgage market data.

    Priority:
      1. SAMA live key rates API (SAIBOR)
      2. CSV Table-8_1 for CPI/inflation
      3. CSV Table-12e for loan market health
      4. CSV Table-12f for mortgage volume/momentum
      5. Fallback constants if all else fails

    Returns:
        {
          "saibor_3m_pct":               float,   # e.g. 5.27
          "saibor_6m_pct":               float,
          "repo_rate_pct":               float,
          "inflation_pct":               float,   # general CPI YoY %
          "housing_cpi_pct":             float,   # housing CPI YoY %
          "re_loans_total_bn_sar":       float,   # total RE loan book SAR bn
          "re_loans_yoy_pct":            float,   # loan book growth %
          "new_mortgages_contracts_latest_q": int,
          "new_mortgages_volume_mn_sar": float,
          "mortgage_growth_pct":         float,   # new mortgage YoY %
          "source":                      str,
          "is_mock":                     False,
        }
    """
    result = dict(_FALLBACK)
    result["is_mock"] = False
    result["as_of"]   = date.today().isoformat()

    # 1. Try live SAIBOR
    live = _fetch_saibor_live()
    if live:
        result.update({k: v for k, v in live.items() if v is not None})
        result["source"] = "sama_live"
        logger.info(f"[sama] Live SAIBOR: 3M={result.get('saibor_3m_pct')}%")
    else:
        logger.info("[sama] Using fallback SAIBOR values")

    # 2. CPI from CSV
    cpi = _parse_table_8_1()
    if cpi:
        result.update({k: v for k, v in cpi.items() if v is not None})
        if result["source"] != "sama_live":
            result["source"] = "sama_csv"

    # 3. RE loan market health
    loans = _parse_table_12e()
    if loans:
        result.update({k: v for k, v in loans.items() if v is not None})

    # 4. Mortgage volumes
    mortgages = _parse_mortgage_volumes()
    if mortgages:
        result.update({k: v for k, v in mortgages.items() if v is not None})

    return result


# ── Derived helpers used by pipeline/financial.py ────────────────────────────

def get_wacc_inputs() -> dict:
    """
    Return inputs for WACC calculation:
      - risk_free_rate:   SAIBOR 3M (proxy for risk-free in SAR)
      - equity_premium:   Saudi market equity risk premium (constant ~5.5%)
      - debt_rate:        typical RE developer borrowing rate (SAIBOR + 200 bps)
    """
    rates = get_financing_rates()
    saibor_3m = rates.get("saibor_3m_pct", _FALLBACK["saibor_3m_pct"])
    return {
        "risk_free_rate_pct":   saibor_3m,
        "equity_risk_premium":  5.5,
        "debt_rate_pct":        round(saibor_3m + 2.0, 2),     # spread ~200 bps
        "source":               rates.get("source", "fallback"),
        "inflation_pct":        rates.get("inflation_pct", _FALLBACK["inflation_pct"]),
    }


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, json
    sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("SAMA Financing Rates & Market Data")
    print("=" * 60)

    data = get_financing_rates()
    print(f"\n📊 Source:         {data['source']}")
    print(f"   SAIBOR 3M:     {data.get('saibor_3m_pct')}%")
    print(f"   SAIBOR 6M:     {data.get('saibor_6m_pct')}%")
    print(f"   Repo Rate:     {data.get('repo_rate_pct')}%")
    print(f"   Inflation CPI: {data.get('inflation_pct')}%")
    print(f"   Housing CPI:   {data.get('housing_cpi_pct')}%")
    print(f"   RE Loans:      {data.get('re_loans_total_bn_sar')} bn SAR "
          f"(YoY {data.get('re_loans_yoy_pct')}%)")
    print(f"   New Mortgages: {data.get('new_mortgages_contracts_latest_q')} contracts "
          f"({data.get('new_mortgages_volume_mn_sar')} bn SAR)")

    print("\n📐 WACC Inputs:")
    wacc = get_wacc_inputs()
    for k, v in wacc.items():
        print(f"   {k}: {v}")
