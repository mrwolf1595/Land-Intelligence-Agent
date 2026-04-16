"""
Price benchmarks: compute and cache avg/median price-per-m² by city+district.

Rebuilt after each scrape cycle from the opportunities table.
Used by the analyzer for market-relative scoring and by financial.py for ROI.
"""

import statistics
from datetime import datetime

from core.database import get_conn
from core.logger import get_logger

logger = get_logger("benchmarks")


def rebuild_benchmarks():
    """Recompute avg/median price-per-m² for every city+district pair."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT city, district, price_sar, area_sqm
        FROM opportunities
        WHERE price_sar > 0 AND area_sqm > 0
        AND duplicate_of IS NULL
    """).fetchall()

    groups: dict[tuple, list] = {}
    for row in rows:
        city = row["city"] or ""
        district = row["district"] or ""
        price = float(row["price_sar"])
        area = float(row["area_sqm"])
        if area <= 0:
            continue
        ppm = price / area
        groups.setdefault((city, district), []).append(ppm)
        groups.setdefault((city, ""), []).append(ppm)   # city-level bucket too

    now = datetime.now().isoformat()
    inserted = 0
    for (city, district), vals in groups.items():
        if len(vals) < 3:
            continue
        conn.execute("""
            INSERT OR REPLACE INTO price_benchmarks
            (city, district, avg_price_per_sqm, median_price_per_sqm,
             sample_count, last_updated)
            VALUES (?,?,?,?,?,?)
        """, (
            city, district,
            sum(vals) / len(vals),
            statistics.median(vals),
            len(vals), now,
        ))
        inserted += 1

    conn.commit()
    conn.close()
    logger.info(f"Benchmarks rebuilt: {inserted} city/district groups from {len(rows)} listings")


def get_benchmark(city: str, district: str = "") -> dict | None:
    """Return benchmark stats for a city+district, or None."""
    conn = get_conn()
    row = conn.execute("""
        SELECT avg_price_per_sqm, median_price_per_sqm, sample_count
        FROM price_benchmarks WHERE city=? AND district=?
    """, (city, district)).fetchone()
    conn.close()
    if row:
        return {"avg": row[0], "median": row[1], "count": row[2]}
    return None
