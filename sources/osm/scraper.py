"""
OpenStreetMap (Overpass API) Integrator.

Fetches nearby amenities (schools, hospitals, mosques, commercial zones, metro stations)
for a given latitude and longitude. Replaces the need for closed GUI GIS municipal systems.
"""
import httpx
from core.logger import get_logger

logger = get_logger("osm_scraper")

def get_nearby_amenities(lat: float, lon: float, radius: int = 1500) -> dict:
    """
    Query Overpass API for amenities within a radius (in meters) of (lat, lon).
    Returns a dictionary of counts.
    """
    overpass_url = "http://overpass-api.de/api/interpreter"
    
    # Overpass QL to find specific amenity types within the radius around a point
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="school"](around:{radius},{lat},{lon});
      node["amenity"="hospital"](around:{radius},{lat},{lon});
      node["amenity"="clinic"](around:{radius},{lat},{lon});
      node["amenity"="place_of_worship"](around:{radius},{lat},{lon});
      node["shop"](around:{radius},{lat},{lon});
      node["public_transport"="station"](around:{radius},{lat},{lon});
      node["leisure"="park"](around:{radius},{lat},{lon});
    );
    out count;
    """
    
    counts = {
        "schools": 0,
        "healthcare": 0,
        "mosques": 0,
        "commercial": 0,
        "transit": 0,
        "parks": 0
    }
    
    if not lat or not lon:
        return counts

    try:
        response = httpx.post(overpass_url, data={"data": query}, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        
        # Overpass 'out count' returns stats per type but we can just parse the tags if we export nodes.
        # Wait, 'out count' returns an object like:
        # { "elements": [ { "type": "count", "id": 0, "tags": {"nodes": X} } ] }
        # It's better to return `out center;` or `out tags;` to count by type. Let's do `out tags;`.
        # Actually I'll rewrite the query to just export nodes with their tags so we can tally them locally.
        
        # Better query for explicit counting:
        query_explicit = f"""
        [out:json][timeout:25];
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
        response = httpx.post(overpass_url, data={"data": query_explicit}, timeout=20.0)
        response.raise_for_status()
        data = response.json()
        
        elements = data.get("elements", [])
        for el in elements:
            tags = el.get("tags", {})
            am = tags.get("amenity", "")
            shop = tags.get("shop", "")
            transport = tags.get("public_transport", "")
            leisure = tags.get("leisure", "")
            
            if am in ["school", "university", "kindergarten"]:
                counts["schools"] += 1
            elif am in ["hospital", "clinic", "pharmacy"]:
                counts["healthcare"] += 1
            elif am == "place_of_worship":
                counts["mosques"] += 1
            elif shop:
                counts["commercial"] += 1
            elif transport == "station":
                counts["transit"] += 1
            elif leisure == "park":
                counts["parks"] += 1

        counts["total_points_of_interest"] = sum(counts.values())
        return counts

    except Exception as e:
        logger.error(f"Error fetching Overpass data for ({lat}, {lon}): {e}")
        return counts

if __name__ == "__main__":
    # Test block using coordinates in Riyadh (near Kingdom Centre, Olaya)
    print("Testing Overpass API integration for (24.7114, 46.6744) - Riyadh Olaya...")
    res = get_nearby_amenities(24.7114, 46.6744, radius=1000)
    print("Amenities found within 1km:")
    for k, v in res.items():
        print(f"  {k}: {v}")
