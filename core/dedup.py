"""
Cross-platform deduplication for scraped land listings.

Two listings are considered duplicates if they share the same city AND
have area within 5% AND price within 10%.  The newer one is marked as
``duplicate_of`` the older one so the dashboard can filter them out.
"""

from core.database import get_conn
from core.logger import get_logger

logger = get_logger("dedup")


def find_duplicate(listing: dict, conn) -> str | None:
    """Return listing_id of existing near-duplicate, or None."""
    city = listing.get("city", "")
    area = float(listing.get("area_sqm") or 0)
    price = float(listing.get("price_sar") or 0)
    if not city or area <= 0 or price <= 0:
        return None

    rows = conn.execute("""
        SELECT id, area_sqm, price_sar FROM opportunities
        WHERE city = ? AND duplicate_of IS NULL
        AND id != ?
    """, (city, listing.get("listing_id", ""))).fetchall()

    for row in rows:
        row_area = float(row["area_sqm"] or 0)
        row_price = float(row["price_sar"] or 0)
        if row_area <= 0 or row_price <= 0:
            continue
        area_diff = abs(row_area - area) / area
        price_diff = abs(row_price - price) / price
        if area_diff < 0.05 and price_diff < 0.10:
            return row["id"]
    return None


def mark_duplicates(conn=None):
    """Run after each scrape to tag newly added duplicates."""
    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    rows = conn.execute("""
        SELECT id, city, area_sqm, price_sar
        FROM opportunities WHERE duplicate_of IS NULL
        ORDER BY created_at DESC LIMIT 500
    """).fetchall()

    tagged = 0
    for row in rows:
        listing = {
            "listing_id": row["id"],
            "city": row["city"],
            "area_sqm": row["area_sqm"],
            "price_sar": row["price_sar"],
        }
        dup = find_duplicate(listing, conn)
        if dup:
            conn.execute(
                "UPDATE opportunities SET duplicate_of=? WHERE id=?",
                (dup, row["id"]),
            )
            tagged += 1

    conn.commit()
    if tagged:
        logger.info(f"Dedup: tagged {tagged} duplicate listings")

    if own_conn:
        conn.close()
