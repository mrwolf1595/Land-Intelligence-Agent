"""
Price benchmarks: compute and cache avg/median price-per-m² by city+district.

Rebuilt after each scrape cycle from the opportunities table.
Used by the analyzer for market-relative scoring and by financial.py for ROI.

Also snapshots price history for trend analysis (Task 4.2).
"""

import statistics
from datetime import datetime, date

from core.database import get_conn
from core.logger import get_logger

logger = get_logger("benchmarks")


def rebuild_benchmarks():
    """Recompute avg/median price-per-m² for every city+district pair.

    Also snapshots to price_history (one snapshot per day max).
    """
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
    today = date.today().isoformat()         # one snapshot per day
    inserted = 0
    for (city, district), vals in groups.items():
        if len(vals) < 3:
            continue
        avg_val = sum(vals) / len(vals)
        conn.execute("""
            INSERT OR REPLACE INTO price_benchmarks
            (city, district, avg_price_per_sqm, median_price_per_sqm,
             sample_count, last_updated)
            VALUES (?,?,?,?,?,?)
        """, (
            city, district,
            avg_val,
            statistics.median(vals),
            len(vals), now,
        ))

        # ── Snapshot to price_history (one per day per city+district) ─────────
        conn.execute("""
            INSERT OR IGNORE INTO price_history
            (city, district, avg_price_per_sqm, sample_count, recorded_at)
            VALUES (?,?,?,?,?)
        """, (city, district, avg_val, len(vals), today))

        inserted += 1

    conn.commit()
    conn.close()
    logger.info(f"Benchmarks rebuilt: {inserted} city/district groups from {len(rows)} listings")


def get_benchmark(city: str, district: str = "") -> dict | None:
    """Return benchmark stats for a city+district, or None.

    Priority (highest → lowest data quality):
      1. market_reference_prices source='moj'       — live API, 19 trending districts
      2. market_reference_prices source='local_moj' — 1.4M CSV transactions, all cities
      3. price_benchmarks                           — scraped ask-prices (fallback)
    """
    conn = get_conn()

    # ── 1. Live MOJ API prices (trending districts — freshest data) ──────────
    ref = conn.execute("""
        SELECT price_per_sqm, sample_count
        FROM market_reference_prices
        WHERE city = ? AND district = ? AND source = 'moj'
    """, (city, district)).fetchone()

    if ref and ref[1] >= 2:
        conn.close()
        return {
            "avg":    ref[0],
            "median": ref[0],
            "count":  ref[1],
            "source": "moj",
        }

    # ── 2. Local MOJ CSV (1.4M transactions — comprehensive city coverage) ───
    ref_local = conn.execute("""
        SELECT price_per_sqm, sample_count
        FROM market_reference_prices
        WHERE city = ? AND district = ? AND source = 'local_moj'
    """, (city, district)).fetchone()

    if ref_local and ref_local[1] >= 3:
        conn.close()
        return {
            "avg":    ref_local[0],
            "median": ref_local[0],
            "count":  ref_local[1],
            "source": "local_moj",
        }

    # ── 3. Fallback: scraped ask-price benchmarks ─────────────────────────────
    row = conn.execute("""
        SELECT avg_price_per_sqm, median_price_per_sqm, sample_count
        FROM price_benchmarks WHERE city=? AND district=?
    """, (city, district)).fetchone()
    conn.close()
    if row:
        return {"avg": row[0], "median": row[1], "count": row[2], "source": "scraped"}
    return None


def get_price_trend(city: str, district: str = "", months: int = 6) -> dict | None:
    """Analyze price direction over the last N months.

    Returns:
        {
            "direction": "UP" | "DOWN" | "STABLE",
            "change_pct": 15.2,
            "monthly_points": [(date, avg_price), ...],
            "data_points": 5,
        }
        or None if insufficient data (< 2 data points).
    """
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=months * 30)).isoformat()

    conn = get_conn()
    rows = conn.execute("""
        SELECT avg_price_per_sqm, recorded_at
        FROM price_history
        WHERE city = ? AND district = ? AND recorded_at >= ?
        ORDER BY recorded_at ASC
    """, (city, district, cutoff)).fetchall()
    conn.close()

    if len(rows) < 2:
        return None

    points = [(r["recorded_at"], float(r["avg_price_per_sqm"])) for r in rows]

    oldest_price = points[0][1]
    newest_price = points[-1][1]

    if oldest_price <= 0:
        return None

    change_pct = ((newest_price - oldest_price) / oldest_price) * 100

    if change_pct > 3:
        direction = "UP"
    elif change_pct < -3:
        direction = "DOWN"
    else:
        direction = "STABLE"

    return {
        "direction": direction,
        "change_pct": round(change_pct, 1),
        "monthly_points": points[-90:],    # last ~3 months of daily points
        "data_points": len(points),
        "oldest_price": oldest_price,
        "newest_price": newest_price,
    }
