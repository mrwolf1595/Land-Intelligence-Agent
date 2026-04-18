"""
Zoning and Building Codes Module.

Reads district-specific FAR (Floor Area Ratio) and building rules so that
financial calculations aren't relying on a flat default.
"""
import json
from pathlib import Path
from core.logger import get_logger

logger = get_logger("zoning")

ZONING_FILE = Path("data/zoning_rules.json")
_ZONING_PULL = None

def _load_zoning() -> dict:
    global _ZONING_PULL
    if _ZONING_PULL is not None:
        return _ZONING_PULL
    
    if not ZONING_FILE.exists():
        logger.warning(f"Zoning file {ZONING_FILE} not found. using defaults.")
        return {}

    try:
        with open(ZONING_FILE, "r", encoding="utf-8") as f:
            _ZONING_PULL = json.load(f)
            return _ZONING_PULL
    except Exception as e:
        logger.error(f"Error reading zoning file: {e}")
        return {}

def get_zoning_rules(city: str, district: str) -> dict:
    """
    Returns the zoning rules (far, max_floors, setback_m) for a city/district.
    Falls back to city defaults, or country defaults.
    """
    zoning_db = _load_zoning()
    
    city_rules = zoning_db.get(city)
    if not city_rules:
        # try to find matching city if there is a partial match
        matched_city = None
        for c in zoning_db.keys():
            if c in city or city in c:
                matched_city = c
                break
        city_rules = zoning_db.get(matched_city) if matched_city else zoning_db.get("default", {})
        
    dist_rules = city_rules.get("districts", {}).get(district)
    if dist_rules:
        return {
            "far": dist_rules.get("far", city_rules.get("default_far", 2.0)),
            "max_floors": dist_rules.get("max_floors", 3),
            "setback_m": dist_rules.get("setback_m", 4),
            "source": f"{city} - {district}"
        }
        
    # fallback to city defaults
    return {
        "far": city_rules.get("default_far", 2.0),
        "max_floors": 3,
        "setback_m": 4,
        "source": f"{city} (Default)"
    }
