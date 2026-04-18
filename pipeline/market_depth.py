"""
Market Depth Analysis.

Analyzes supply and demand to determine if an area is saturated or active.
Counts active listings over the last 90 days vs the last 30 days.

High months_of_inventory means it might be very hard to sell what we build.
"""
from core.database import get_conn
from core.logger import get_logger

logger = get_logger("market_depth")


def analyze_market_depth(city: str, district: str) -> dict:
    """
    Returns market depth metrics for a given city and district.
    We proxy 'active listings' via listings seen recently (30 days)
    and 'absorption proxy' via older listings (30-90 days).
    """
    if not city:
        return {"market_condition": "UNKNOWN"}

    conn = get_conn()

    # Active listing proxy: scraped within last 30 days
    # Since created_at is when we first scraped it (due to INSERT OR IGNORE)
    # this will capture new listings added in the last 30 days.
    active_row = conn.execute("""
        SELECT COUNT(*) FROM opportunities 
        WHERE city=? AND (district=? OR ?='') 
        AND created_at >= date('now', '-30 days')
        AND duplicate_of IS NULL
    """, (city, district, district)).fetchone()
    
    recent_new_listings = active_row[0] if active_row else 0

    # Historic listings (30-90 days ago)
    historic_row = conn.execute("""
        SELECT COUNT(*) FROM opportunities 
        WHERE city=? AND (district=? OR ?='') 
        AND created_at BETWEEN date('now', '-90 days') AND date('now', '-30 days')
        AND duplicate_of IS NULL
    """, (city, district, district)).fetchone()
    
    older_listings = historic_row[0] if historic_row else 0

    conn.close()

    # If we have lots of old listings and zero new ones, maybe market is dead
    # If we have lots of new ones and zero old ones, market is hot / just started scraping

    # A more sophisticated check needs actual "sold" flags.
    # For now, we measure sheer volume of supply.
    
    total_supply = recent_new_listings + older_listings
    
    condition = "BALANCED"
    supply_pressure = 0
    
    if total_supply > 300:
        condition = "OVERSUPPLIED"
        supply_pressure = 2  # high penalty
    elif total_supply > 150:
        condition = "OVERSUPPLIED"
        supply_pressure = 1  # mid penalty
    elif total_supply < 20 and total_supply > 5:
        condition = "LOW_SUPPLY"
        supply_pressure = -1 # positive indicator
        
    return {
        "recent_entries_30d": recent_new_listings,
        "older_entries_90d": older_listings,
        "total_known_supply": total_supply,
        "market_condition": condition,
        "supply_penalty": supply_pressure
    }
