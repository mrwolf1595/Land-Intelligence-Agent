"""
OpenStreetMap (Overpass API) Integrator.

Fetches nearby amenities (schools, hospitals, mosques, commercial zones, metro stations)
for a given latitude and longitude.

Mirrors tried in order (first success wins):
  1. https://overpass-api.de/api/interpreter       (main)
  2. https://overpass.kumi.systems/api/interpreter  (EU mirror)
  3. https://overpass.openstreetmap.ru/api/interpreter (RU mirror)
"""
import httpx
from core.logger import get_logger

logger = get_logger("osm_scraper")

_MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

_QUERY_TEMPLATE = """
[out:json][timeout:30];
(
  node["amenity"~"school|university|kindergarten"](around:{radius},{lat},{lon});
  node["amenity"~"hospital|clinic|pharmacy"](around:{radius},{lat},{lon});
  node["amenity"="place_of_worship"](around:{radius},{lat},{lon});
  node["shop"](around:{radius},{lat},{lon});
  node["public_transport"="station"](around:{radius},{lat},{lon});
  node["leisure"="park"](around:{radius},{lat},{lon});
);
out tags;
"""

_EMPTY = {
    "schools": 0, "healthcare": 0, "mosques": 0,
    "commercial": 0, "transit": 0, "parks": 0,
    "total_points_of_interest": 0,
}


def get_nearby_amenities(lat: float, lon: float, radius: int = 1500) -> dict:
    """
    Query Overpass API for amenities within a radius (in meters) of (lat, lon).
    Tries multiple mirrors with fallback. Returns a dict of counts.
    """
    if not lat or not lon:
        return dict(_EMPTY)

    query = _QUERY_TEMPLATE.format(radius=radius, lat=lat, lon=lon)
    counts = dict(_EMPTY)

    for mirror in _MIRRORS:
        try:
            response = httpx.post(
                mirror,
                data={"data": query},
                timeout=35.0,
                headers={"User-Agent": "LandIntelligenceAgent/1.0"},
            )
            response.raise_for_status()
            elements = response.json().get("elements", [])

            for el in elements:
                tags = el.get("tags", {})
                am       = tags.get("amenity", "")
                shop     = tags.get("shop", "")
                transport = tags.get("public_transport", "")
                leisure  = tags.get("leisure", "")

                if am in ("school", "university", "kindergarten"):
                    counts["schools"] += 1
                elif am in ("hospital", "clinic", "pharmacy"):
                    counts["healthcare"] += 1
                elif am == "place_of_worship":
                    counts["mosques"] += 1
                elif shop:
                    counts["commercial"] += 1
                elif transport == "station":
                    counts["transit"] += 1
                elif leisure == "park":
                    counts["parks"] += 1

            counts["total_points_of_interest"] = sum(
                v for k, v in counts.items() if k != "total_points_of_interest"
            )
            return counts   # success — no need to try other mirrors

        except httpx.TimeoutException:
            logger.debug(f"[osm] Timeout on {mirror} — trying next mirror")
        except Exception as e:
            logger.debug(f"[osm] Error on {mirror}: {e}")

    # All mirrors failed
    logger.warning(f"[osm] All Overpass mirrors failed for ({lat:.4f}, {lon:.4f}) — skipping amenities")
    return counts


if __name__ == "__main__":
    print("Testing Overpass API — Riyadh Olaya (24.7114, 46.6744)")
    res = get_nearby_amenities(24.7114, 46.6744, radius=1000)
    for k, v in res.items():
        print(f"  {k}: {v}")
