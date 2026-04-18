"""
Local Data Integration — civillizard/Saudi-Real-Estate-Data
============================================================
Imports offline government datasets (MOJ transactions, REGA rentals,
KAPSARC price index, GASTAT REPI) into SQLite, making them available
to the analysis pipeline.

Data source: Saudi-Real-Estate-Data/ (cloned repo in project root)
             9.5M records · 2014-2026 · MOJ + REGA + KAPSARC + SAMA + GASTAT

Import priority for get_benchmark():
  1. local_moj  — 1.4M closed transactions, all cities/districts (most comprehensive)
  2. moj API    — live ~19 trending districts (freshest, but narrow coverage)
  3. scraped    — ask-prices from Aqar/Haraj (least trusted)

Tables populated by this module:
  market_reference_prices  (source='local_moj')
  rental_benchmarks        (new)
  price_index_history      (extended — source='kapsarc')
  repi_index               (new — GASTAT regional price index)
  data_import_log          (new — import state tracking)
"""

import csv
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.database import get_conn
from core.logger import get_logger

logger = get_logger("local_data")

# ── Paths ─────────────────────────────────────────────────────────────────────
_REPO = Path(__file__).parent.parent / "Saudi-Real-Estate-Data"

# ── Typical unit floor areas (m²) — used to derive rent/m² from REGA data ────
_UNIT_AREAS: dict[str, int] = {
    "استديو":       45,
    "شقة":         110,
    "دور":         260,
    "فيلا":        350,
    "دوبلاكس":     200,
    "دوبلكس":      200,
    "محل":          60,
    "مكتب":         80,
    "معرض تجاري":  120,
}

# ── City/region name normalization ────────────────────────────────────────────
_STRIP_PREFIXES = [
    "منطقة ", "إمارة ", "مدينة ",
    " الإدارية", " المكرمه", " المكرمة", " المنورة",
]

# Maps MOJ-specific/alternative spellings → canonical Arabic city name
# (MOJ data uses colloquial ه endings; Aqar/REGA use standard ة)
_CITY_ALIASES: dict[str, str] = {
    # Major cities — ه → ة
    "جده":            "جدة",
    "مكه":            "مكة",
    "مكه المكرمه":    "مكة",
    "بريده":          "بريدة",
    "عنيزه":          "عنيزة",
    "الرسه":          "الرسة",
    "المجمعه":        "المجمعة",
    "رابغه":          "رابغ",
    "المدينه":        "المدينة المنورة",
    "الالمنورة":      "المدينة المنورة",
    "المنوره":        "المدينة المنورة",
    # Missing hamza
    "ابها":           "أبها",
    "ابوعريش":        "أبو عريش",
    "ابو عريش":       "أبو عريش",
    # Ejar API spellings (colloquial ه ending)
    "المدينه المنوره": "المدينة المنورة",
    "المدينه":         "المدينة المنورة",
    "حائل ":           "حائل",
    "بريده ":          "بريدة",
    # Alternate common names
    "جيزان":           "جازان",
    "الاحساء":        "الأحساء",
    "الاحسا":         "الأحساء",
    "القطيف":         "القطيف",
    "الهفوف":         "الأحساء",   # Hofuf is the main city of Al-Ahsa
    "الظهران":        "الدمام",    # Dhahran often grouped with Dammam metro
    "رفحاء":          "رفحاء",
    "سكاكا":          "سكاكا",
}

def _norm(name: str) -> str:
    """
    Normalize city name:
    1. Strip whitespace and redundant region prefixes
    2. Apply known alias mappings for consistent cross-source matching
    """
    s = (name or "").strip()
    for tok in _STRIP_PREFIXES:
        s = s.replace(tok, "")
    s = s.strip()
    return _CITY_ALIASES.get(s, s)


def _parse_price(raw) -> float:
    """Parse '1,234,567' or '1234567' to float safely."""
    try:
        return float(str(raw).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _parse_district(city_district: str) -> str:
    """
    Extract district from 'City / District' combined field.
    'الرياض/الزهراء'       → 'الزهراء'
    'الطائف/ الجودية '     → 'الجودية'
    'الرياض'               → ''
    """
    cd = city_district or ""
    if "/" not in cd:
        return ""
    return cd.split("/", 1)[1].strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. MOJ Sales CSV → market_reference_prices (source = 'local_moj')
# ═══════════════════════════════════════════════════════════════════════════════

def import_moj_local_benchmarks(force: bool = False) -> int:
    """
    Read all MOJ-Sales-*.csv files (1.4M rows, 2020-2025) and upsert
    aggregated price/m² benchmarks into market_reference_prices.

    • Aggregates on-the-fly — does NOT store individual transactions.
    • Skips if already imported today (unless force=True).
    • Returns: number of (city, district) groups upserted.
    """
    conn = get_conn()

    if not force:
        row = conn.execute(
            "SELECT imported_at FROM data_import_log WHERE source='local_moj'"
        ).fetchone()
        if row and row["imported_at"] and row["imported_at"][:10] == datetime.now().strftime("%Y-%m-%d"):
            conn.close()
            logger.info("MOJ local benchmarks: already imported today — skipping")
            return 0

    sales_dir = _REPO / "moj" / "sales"
    if not sales_dir.exists():
        logger.error(f"MOJ sales directory not found: {sales_dir}")
        conn.close()
        return 0

    # Accumulate [price_per_m²] per (city, district)
    groups: dict[tuple, list] = defaultdict(list)
    total_rows = 0
    skipped = 0

    for csv_file in sorted(sales_dir.glob("MOJ-Sales-*.csv")):
        try:
            with open(csv_file, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    price = _parse_price(row.get("السعر", ""))
                    area  = _parse_price(row.get("المساحة", ""))
                    city  = _norm(row.get("المدينة", ""))

                    if price <= 0 or area <= 0 or not city:
                        skipped += 1
                        continue

                    ppm = price / area   # SAR / m²

                    # Sanity bounds: SAR 50–200,000/m² covers all Saudi markets
                    if not (50 <= ppm <= 200_000):
                        skipped += 1
                        continue

                    district = _parse_district(row.get("المدينة / الحي", ""))

                    groups[(city, district)].append(ppm)
                    groups[(city, "")].append(ppm)      # city-level bucket too
                    total_rows += 1

        except Exception as exc:
            logger.error(f"[local_moj] Error reading {csv_file.name}: {exc}")

    now = datetime.now().isoformat()
    inserted = 0

    for (city, district), vals in groups.items():
        if len(vals) < 3:
            continue
        avg_val    = sum(vals) / len(vals)
        median_val = statistics.median(vals)
        try:
            conn.execute("""
                INSERT INTO market_reference_prices
                    (city, district, price_per_sqm, source,
                     transaction_date, sample_count, created_at)
                VALUES (?, ?, ?, 'local_moj', ?, ?, ?)
                ON CONFLICT(city, district, source) DO UPDATE SET
                    price_per_sqm    = excluded.price_per_sqm,
                    transaction_date = excluded.transaction_date,
                    sample_count     = excluded.sample_count,
                    created_at       = excluded.created_at
            """, (city, district, round(avg_val, 2), now[:10], len(vals), now))
            inserted += 1
        except Exception as exc:
            logger.error(f"[local_moj] DB error {city}/{district}: {exc}")

    # Remove stale rows for old/un-normalized city names
    for old_name in _CITY_ALIASES:
        conn.execute(
            "DELETE FROM market_reference_prices WHERE city=? AND source='local_moj'",
            (old_name,)
        )

    _log_import(conn, "local_moj", now, inserted)
    conn.commit()
    conn.close()

    logger.info(
        f"[local_moj] {inserted:,} city/district groups  |  "
        f"{total_rows:,} transactions processed  |  {skipped:,} skipped"
    )
    return inserted


# ═══════════════════════════════════════════════════════════════════════════════
# 2. REGA Rental Indicators → rental_benchmarks
# ═══════════════════════════════════════════════════════════════════════════════

def import_rega_rental_data(force: bool = False) -> int:
    """
    Load all REGA Rental-indicators-*.csv files into rental_benchmarks.
    Groups by (city, property_type_ar), stores average annual rent/unit.

    المتوسط column = average annual rent in SAR per unit.
    """
    conn = get_conn()

    if not force:
        row = conn.execute(
            "SELECT imported_at FROM data_import_log WHERE source='rega_rental'"
        ).fetchone()
        if row and row["imported_at"] and row["imported_at"][:10] == datetime.now().strftime("%Y-%m-%d"):
            conn.close()
            logger.info("REGA rental: already imported today — skipping")
            return 0

    rega_dir = _REPO / "rega"
    if not rega_dir.exists():
        logger.error(f"REGA directory not found: {rega_dir}")
        conn.close()
        return 0

    # city+type → list of (annual_rent, weight)
    groups: dict[tuple, list] = defaultdict(list)
    total_rows = 0

    for csv_file in rega_dir.glob("Rental-*.csv"):
        try:
            with open(csv_file, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    city      = (row.get("المدينة") or "").strip()
                    prop_type = (row.get("نوع العقار") or "").strip()
                    try:
                        count    = int(float(row.get("مجموع الصفقات") or 0))
                        avg_rent = float(row.get("المتوسط") or 0)
                    except (ValueError, TypeError):
                        continue

                    if not city or avg_rent <= 100 or count < 1:
                        continue

                    # Weight by transaction count (capped to avoid single-source domination)
                    weight = min(count, 50)
                    groups[(city, prop_type)].extend([avg_rent] * weight)
                    total_rows += 1

        except Exception as exc:
            logger.error(f"[rega_rental] Error reading {csv_file.name}: {exc}")

    now = datetime.now().isoformat()
    inserted = 0

    for (city, prop_type), rents in groups.items():
        if not rents:
            continue
        avg_annual = round(sum(rents) / len(rents), 2)

        # Derive property category
        category = "تجاري" if "تجاري" in prop_type else "سكني"

        # Estimate rent per m²/year using typical unit area
        base_type = prop_type.split(" - ")[0].strip()
        area_est  = _UNIT_AREAS.get(base_type, 100)
        rent_per_sqm = round(avg_annual / area_est, 2)

        try:
            conn.execute("""
                INSERT INTO rental_benchmarks
                    (city, district, property_type_ar, property_category,
                     avg_annual_rent_sar, rent_per_sqm_year,
                     typical_area_sqm, sample_count, source, last_updated)
                VALUES (?, '', ?, ?, ?, ?, ?, ?, 'rega', ?)
                ON CONFLICT(city, district, property_type_ar) DO UPDATE SET
                    avg_annual_rent_sar = excluded.avg_annual_rent_sar,
                    rent_per_sqm_year   = excluded.rent_per_sqm_year,
                    sample_count        = excluded.sample_count,
                    last_updated        = excluded.last_updated
            """, (
                city, prop_type, category,
                avg_annual, rent_per_sqm,
                area_est, len(rents), now,
            ))
            inserted += 1
        except Exception as exc:
            logger.error(f"[rega_rental] DB error {city}/{prop_type}: {exc}")

    # Seed reference estimates for major metros not covered by REGA
    seed_count = _seed_major_city_rent_estimates(conn, now)

    _log_import(conn, "rega_rental", now, inserted + seed_count)
    conn.commit()
    conn.close()

    logger.info(f"[rega_rental] {inserted} city/type groups from {total_rows:,} rows  +  {seed_count} major-city estimates")
    return inserted + seed_count


# ── Major metro rent estimates ────────────────────────────────────────────────
# REGA Ejar data focuses on secondary cities.
# Major metros (Riyadh, Jeddah, Dammam) use reference market estimates
# based on published Aqar/Haraj/CBRE/JLL Saudi market reports.
# Source: 'market_estimate' — treated as lower-priority than real REGA data.

_METRO_RENT_ESTIMATES: dict[str, dict] = {
    "الرياض":          {"شقة": 48_000, "فيلا": 100_000, "محل": 72_000, "مكتب": 66_000},
    "جدة":             {"شقة": 44_000, "فيلا":  90_000, "محل": 65_000, "مكتب": 60_000},
    "مكة":             {"شقة": 40_000, "فيلا":  80_000, "محل": 60_000, "مكتب": 55_000},
    "المدينة المنورة": {"شقة": 32_000, "فيلا":  65_000, "محل": 48_000, "مكتب": 44_000},
    "الدمام":          {"شقة": 36_000, "فيلا":  72_000, "محل": 54_000, "مكتب": 50_000},
    "الخبر":           {"شقة": 40_000, "فيلا":  78_000, "محل": 58_000, "مكتب": 52_000},
    "الأحساء":         {"شقة": 24_000, "فيلا":  50_000, "محل": 36_000, "مكتب": 32_000},
}

def _seed_major_city_rent_estimates(conn, timestamp: str) -> int:
    """Insert reference rent estimates for major metros missing from REGA data.
    Only inserts if no existing REGA row for that city+type combo."""
    count = 0
    for city, types in _METRO_RENT_ESTIMATES.items():
        # Skip if this city already has real REGA data
        existing = conn.execute(
            "SELECT 1 FROM rental_benchmarks WHERE city=? AND source='rega' LIMIT 1",
            (city,)
        ).fetchone()
        if existing:
            continue   # real REGA data takes priority

        for type_ar, annual_rent in types.items():
            area_est = _UNIT_AREAS.get(type_ar, 100)
            try:
                conn.execute("""
                    INSERT INTO rental_benchmarks
                        (city, district, property_type_ar, property_category,
                         avg_annual_rent_sar, rent_per_sqm_year,
                         typical_area_sqm, sample_count, source, last_updated)
                    VALUES (?, '', ?, ?, ?, ?, ?, 0, 'market_estimate', ?)
                    ON CONFLICT(city, district, property_type_ar) DO NOTHING
                """, (
                    city,
                    type_ar,
                    "تجاري" if type_ar in ("محل", "مكتب") else "سكني",
                    annual_rent,
                    round(annual_rent / area_est, 2),
                    area_est,
                    timestamp,
                ))
                count += 1
            except Exception as exc:
                logger.error(f"Metro seed error {city}/{type_ar}: {exc}")
    return count


# ═══════════════════════════════════════════════════════════════════════════════
# 3. KAPSARC Price Index → price_index_history (source = 'kapsarc')
# ═══════════════════════════════════════════════════════════════════════════════

def import_kapsarc_index(force: bool = False) -> int:
    """
    Import KAPSARC quarterly real-estate price index (2023 base year).
    Stored in price_index_history with source='kapsarc'.
    Only the 'Index' measure is imported (QoQ/YoY can be derived).
    """
    conn = get_conn()

    if not force:
        row = conn.execute(
            "SELECT imported_at FROM data_import_log WHERE source='kapsarc'"
        ).fetchone()
        if row and row["imported_at"] and row["imported_at"][:10] == datetime.now().strftime("%Y-%m-%d"):
            conn.close()
            logger.info("KAPSARC: already imported today — skipping")
            return 0

    csv_file = _REPO / "kapsarc" / "KAPSARC-RE-Price-Index-2023base.csv"
    if not csv_file.exists():
        logger.error(f"KAPSARC file not found: {csv_file}")
        conn.close()
        return 0

    now = datetime.now().isoformat()
    inserted = 0

    try:
        with open(csv_file, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh, delimiter=";"):
                try:
                    year    = int(row.get("year") or 0)
                    quarter = (row.get("quarter") or "-").strip()
                    measure = (row.get("measure") or "").strip()
                    sector  = (row.get("sector") or "").strip()
                    value   = float(row.get("value") or 0)
                except (ValueError, TypeError):
                    continue

                # Only import Index values; skip QoQ/YoY (derivable)
                if not year or not sector or measure != "Index":
                    continue

                conn.execute("""
                    INSERT OR REPLACE INTO price_index_history
                        (year, quarter, sector, index_value, base_year, source)
                    VALUES (?, ?, ?, ?, 2023, 'kapsarc')
                """, (year, quarter, sector, value))
                inserted += 1

    except Exception as exc:
        logger.error(f"[kapsarc] Import error: {exc}")

    _log_import(conn, "kapsarc", now, inserted)
    conn.commit()
    conn.close()

    logger.info(f"[kapsarc] {inserted} index records imported")
    return inserted


# ═══════════════════════════════════════════════════════════════════════════════
# 4. GASTAT REPI → repi_index
# ═══════════════════════════════════════════════════════════════════════════════

def import_gastat_repi(force: bool = False) -> int:
    """
    Import GASTAT Real-Estate Price Index (REPI) quarterly CSV files.
    Provides regional price trend signals with YoY/QoQ change rates.

    yoy_change_pct and qoq_change_pct in CSV are ratios (0.10 = 10%) → ×100.
    """
    conn = get_conn()

    if not force:
        row = conn.execute(
            "SELECT imported_at FROM data_import_log WHERE source='gastat_repi'"
        ).fetchone()
        if row and row["imported_at"] and row["imported_at"][:10] == datetime.now().strftime("%Y-%m-%d"):
            conn.close()
            logger.info("GASTAT REPI: already imported today — skipping")
            return 0

    gastat_dir = _REPO / "gastat"
    repi_files = sorted(gastat_dir.glob("REPI-*.csv"))

    if not repi_files:
        logger.error(f"No REPI CSV files found in {gastat_dir}")
        conn.close()
        return 0

    now = datetime.now().isoformat()
    inserted = 0

    for csv_file in repi_files:
        try:
            with open(csv_file, encoding="utf-8-sig") as fh:
                for row in csv.DictReader(fh):
                    try:
                        year     = int(row.get("السنة") or 0)
                        quarter  = (row.get("التاريخ") or "").strip()    # '2025 / Q1'
                        region   = (row.get("المنطقة الإدارية") or "").strip()
                        cat_code = (row.get("رمز البند") or "").strip()
                        cat_name = (row.get("البند") or "").strip()
                        idx_val  = float(row.get("الرقم القياسي") or 0)
                        yoy      = float(row.get("نسبة التغير السنوي") or 0)
                        qoq      = float(row.get("نسبة التغير الربعي") or 0)
                    except (ValueError, TypeError):
                        continue

                    if not year or not region or not cat_code:
                        continue

                    conn.execute("""
                        INSERT OR REPLACE INTO repi_index
                            (year, quarter, region, category_code, category_name,
                             index_value, yoy_change_pct, qoq_change_pct)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        year, quarter, region, cat_code, cat_name,
                        idx_val,
                        round(yoy * 100, 3),   # ratio → percentage
                        round(qoq * 100, 3),
                    ))
                    inserted += 1

        except Exception as exc:
            logger.error(f"[repi] Error reading {csv_file.name}: {exc}")

    _log_import(conn, "gastat_repi", now, inserted)
    conn.commit()
    conn.close()

    logger.info(f"[gastat_repi] {inserted} records from {len(repi_files)} files")
    return inserted


# ═══════════════════════════════════════════════════════════════════════════════
# Query functions — used by financial.py, benchmarks.py, analyzer.py
# ═══════════════════════════════════════════════════════════════════════════════

def get_rental_rate(city: str, prop_type_ar: str = "شقة") -> Optional[float]:
    """
    Return average annual rent (SAR/unit) for a property type in a city.
    Falls back to national average for that property type if city not found.

    Args:
        city:         Arabic city name (e.g. 'الرياض')
        prop_type_ar: Arabic property type keyword (e.g. 'شقة', 'فيلا', 'محل')

    Returns: annual rent in SAR, or None if no data available.
    """
    conn = get_conn()
    base_type = prop_type_ar.split(" - ")[0].strip()

    # 1. Exact city + type match
    row = conn.execute("""
        SELECT avg_annual_rent_sar
        FROM rental_benchmarks
        WHERE city = ? AND property_type_ar LIKE ?
        ORDER BY sample_count DESC LIMIT 1
    """, (city, f"%{base_type}%")).fetchone()

    if not row:
        # 2. National average for same type
        row = conn.execute("""
            SELECT AVG(avg_annual_rent_sar)
            FROM rental_benchmarks
            WHERE property_type_ar LIKE ?
        """, (f"%{base_type}%",)).fetchone()

    conn.close()
    if row and row[0]:
        return float(row[0])
    return None


def get_rental_yield_pct(city: str, district: str = "") -> Optional[float]:
    """
    Calculate expected annual rental yield % for a location.

    Formula: (avg_annual_apt_rent / (avg_price_per_sqm × typical_apt_area)) × 100
    Uses شقة (apartment) as the proxy unit — most common build type.

    Returns: yield % (e.g. 5.5 for 5.5%), or None if data unavailable.
    """
    from pipeline.benchmarks import get_benchmark
    bench = get_benchmark(city, district) or get_benchmark(city, "")
    if not bench or bench["avg"] <= 0:
        return None

    avg_rent = get_rental_rate(city, "شقة")
    if not avg_rent:
        return None

    apt_area       = _UNIT_AREAS["شقة"]               # 110 m²
    apt_sale_price = bench["avg"] * apt_area           # estimated sale value

    if apt_sale_price <= 0:
        return None

    return round((avg_rent / apt_sale_price) * 100, 2)


def get_national_price_trend() -> Optional[dict]:
    """
    Return the latest KAPSARC national RE price index and QoQ movement.

    Returns:
        {
          "latest_index": 95.4,
          "prev_index":   93.1,
          "qoq_pct":       2.5,
          "year": 2024, "quarter": "Q3",
          "direction": "UP"             # UP / DOWN / STABLE
        }
    or None if no data.
    """
    conn = get_conn()
    rows = conn.execute("""
        SELECT year, quarter, index_value
        FROM price_index_history
        WHERE sector = 'Index number' AND source = 'kapsarc'
        ORDER BY year DESC, quarter DESC
        LIMIT 2
    """).fetchall()
    conn.close()

    if len(rows) < 2:
        return None

    latest = rows[0]
    prev   = rows[1]
    qoq    = ((latest["index_value"] - prev["index_value"]) / prev["index_value"]) * 100

    direction = "UP" if qoq > 1 else ("DOWN" if qoq < -1 else "STABLE")

    return {
        "latest_index": latest["index_value"],
        "prev_index":   prev["index_value"],
        "qoq_pct":      round(qoq, 2),
        "year":         latest["year"],
        "quarter":      latest["quarter"],
        "direction":    direction,
    }


def get_repi_for_city(city: str) -> Optional[dict]:
    """
    Return latest GASTAT REPI data for the region containing this city.
    Uses the المملكة (national) general index as fallback.

    Returns:
        {
          "region": "الرياض",
          "index": 114.89,
          "yoy_pct": 10.66,
          "qoq_pct":  1.38,
          "quarter": "2025 / Q1",
          "direction": "UP"
        }
    or None.
    """
    # Map common city names to region names used in REPI files
    _CITY_TO_REGION = {
        "الرياض": "الرياض",
        "جدة":    "مكة المكرمة",
        "مكة":    "مكة المكرمة",
        "الطائف": "مكة المكرمة",
        "المدينة": "المدينة المنورة",
        "الدمام": "المنطقة الشرقية",
        "الخبر":  "المنطقة الشرقية",
        "الأحساء":"المنطقة الشرقية",
        "أبها":   "عسير",
        "تبوك":   "تبوك",
        "بريدة":  "القصيم",
        "حائل":   "حائل",
        "جازان":  "جازان",
        "نجران":  "نجران",
        "الباحة": "الباحة",
    }

    region = _CITY_TO_REGION.get(city, "المملكة")

    conn = get_conn()
    row = conn.execute("""
        SELECT region, index_value, yoy_change_pct, qoq_change_pct, quarter
        FROM repi_index
        WHERE region = ? AND category_code = '0'
        ORDER BY year DESC, quarter DESC
        LIMIT 1
    """, (region,)).fetchone()

    if not row:
        # Fallback to national
        row = conn.execute("""
            SELECT region, index_value, yoy_change_pct, qoq_change_pct, quarter
            FROM repi_index
            WHERE region = 'المملكة' AND category_code = '0'
            ORDER BY year DESC, quarter DESC
            LIMIT 1
        """).fetchone()

    conn.close()
    if not row:
        return None

    yoy = row["yoy_change_pct"]
    return {
        "region":    row["region"],
        "index":     row["index_value"],
        "yoy_pct":   round(yoy, 2),
        "qoq_pct":   round(row["qoq_change_pct"], 2),
        "quarter":   row["quarter"],
        "direction": "UP" if yoy > 2 else ("DOWN" if yoy < -2 else "STABLE"),
    }


def get_import_status() -> list[dict]:
    """Return import log — useful for dashboard diagnostics."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT source, imported_at, record_count FROM data_import_log ORDER BY imported_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _log_import(conn, source: str, timestamp: str, count: int):
    conn.execute("""
        INSERT INTO data_import_log (source, imported_at, record_count)
        VALUES (?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            imported_at  = excluded.imported_at,
            record_count = excluded.record_count
    """, (source, timestamp, count))


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point — called once at agent startup from main.py
# ═══════════════════════════════════════════════════════════════════════════════

def run_all_imports(force: bool = False) -> dict:
    """
    Run all local data imports in sequence.
    Safe to call every startup — each import skips if already done today.

    Args:
        force: Re-import even if already done today (useful after repo pull).

    Returns:
        { "moj": n, "rega": n, "kapsarc": n, "repi": n }
    """
    if not _REPO.exists():
        logger.warning(
            f"Saudi-Real-Estate-Data repo not found at: {_REPO}\n"
            "Skipping local data import. Clone with:\n"
            "  git clone https://github.com/civillizard/Saudi-Real-Estate-Data.git"
        )
        return {}

    logger.info(f"Starting local data imports from: {_REPO}")

    results = {
        "moj":     import_moj_local_benchmarks(force=force),
        "rega":    import_rega_rental_data(force=force),
        "kapsarc": import_kapsarc_index(force=force),
        "repi":    import_gastat_repi(force=force),
    }

    total = sum(results.values())
    logger.info(
        f"Local data import complete — "
        f"MOJ={results['moj']:,} groups | REGA={results['rega']} groups | "
        f"KAPSARC={results['kapsarc']} records | REPI={results['repi']} records "
        f"(total: {total:,})"
    )
    return results
