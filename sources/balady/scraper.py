"""
منصة بلدي (Balady) — ArcGIS REST Scraper
==========================================
Source:  https://umaps.balady.gov.sa
Proxy:   https://umaps.balady.gov.sa/newProxyUDP/proxy.ashx?{arcgis_url}
Backend: https://umapsudp.momrah.gov.sa/server/rest/services/Umaps/

Endpoints used:
  UMaps_AdministrativeData/MapServer/0/query  → district name (DISTRICTNAME_AR)
  UMaps_AdministrativeData/MapServer/2/query  → city name    (CITYNAME_AR, MOJ_CITYID)
  Umaps_Identify_Satatistics6/MapServer/28/query → parcel zoning data
    fields: MAINLANDUSE, MAINLANDUSEDESCRIPTION, NOOFFLOORS,
            HEIGHTCONDITION, MEASUREDAREA, ISCOMMERCIAL, PARCELSTATUS

Auth:     None (public via proxy — requires Referer: umaps.balady.gov.sa)
Limit:    Single envelope query per property (100m buffer around lat/lon)

MAINLANDUSE code → Arabic description (observed in-field):
  100000  سكني          200000  تجاري
  300000  سكني/خدمات    400000  (mixed/unknown)
  800000  ترويحي وحدائق  5555   خدمات (educational/warehouses)
  1000000 تجاري (variant)

Note on NOOFFLOORS: Returns 0–3 floors allowed. null = no restriction recorded.
Note on HEIGHTCONDITION: Usually null in Riyadh residential; populated in special zones.
"""

import json
import math
import time
import urllib.parse
from typing import Optional

import httpx

from core.logger import get_logger

logger = get_logger("balady")

# ── Constants ─────────────────────────────────────────────────────────────────

_PROXY   = "https://umaps.balady.gov.sa/newProxyUDP/proxy.ashx?"
_UMAPS   = "https://umapsudp.momrah.gov.sa/server/rest/services/Umaps/"
_ADMIN   = _UMAPS + "UMaps_AdministrativeData/MapServer"
_PARCEL  = _UMAPS + "Umaps_Identify_Satatistics6/MapServer"

_HEADERS = {
    "Referer":    "https://umaps.balady.gov.sa/",
    "Origin":     "https://umaps.balady.gov.sa",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "application/json",
}

_ENVELOPE_BUFFER_M = 100   # 100 m buffer around target point for parcel lookup

# Observed MAINLANDUSE code → canonical Arabic land-use label
_LANDUSE_CODES: dict[int, str] = {
    100000:  "سكني",
    200000:  "تجاري",
    300000:  "سكني",        # residential variant / خدمات حكومية depending on zone
    400000:  "مختلط",
    800000:  "ترويحي وحدائق",
    5555:    "خدمات",
    1000000: "تجاري",
}

# ── Coordinate conversion ─────────────────────────────────────────────────────

def _to_web_mercator(lat: float, lon: float) -> tuple[float, float]:
    """Convert WGS-84 (lat, lon) → Web Mercator (EPSG:3857 / wkid 102100)."""
    x = lon * 20_037_508.34 / 180.0
    y = (math.log(math.tan((90.0 + lat) * math.pi / 360.0))
         / (math.pi / 180.0)) * 20_037_508.34 / 180.0
    return x, y


# ── HTTP helper ───────────────────────────────────────────────────────────────

def _query(service_path: str, layer_id: int, params: dict,
           client: httpx.Client) -> Optional[dict]:
    """
    Send a GET query to an Umaps ArcGIS layer through the public proxy.

    The proxy format is: proxy.ashx?{full_arcgis_url_with_params}
    The ArcGIS URL and its params must be appended as a raw string after
    the proxy's own '?' — NOT as separate httpx params (which would add a
    second '?' and break the proxy URL).
    """
    all_params = {**params, "f": "json"}
    # Serialize geometry dicts to JSON if they're dict objects
    for k, v in all_params.items():
        if isinstance(v, dict):
            all_params[k] = json.dumps(v, separators=(",", ":"))

    arcgis_path    = f"{service_path}/{layer_id}/query"
    query_string   = urllib.parse.urlencode(all_params, quote_via=urllib.parse.quote)
    arcgis_full    = f"{arcgis_path}?{query_string}"
    proxy_url      = _PROXY + arcgis_full          # proxy.ashx?https://...query?f=json&...

    try:
        r = client.get(proxy_url)
        if r.status_code == 200:
            data = r.json()
            if data.get("error"):
                logger.debug(f"[balady] ArcGIS error layer {layer_id}: {data['error'].get('message')}")
                return None
            return data
        logger.warning(f"[balady] HTTP {r.status_code} for layer {layer_id}")
    except Exception as e:
        logger.error(f"[balady] query error layer {layer_id}: {e}")
    return None


# ── Core lookup functions ─────────────────────────────────────────────────────

def _point_params(lat: float, lon: float, out_fields: str) -> dict:
    """Build ArcGIS point query params (geometry as dict — serialized in _query)."""
    x, y = _to_web_mercator(lat, lon)
    return {
        "geometry":       {"spatialReference": {"wkid": 102100}, "x": x, "y": y},
        "geometryType":   "esriGeometryPoint",
        "inSR":           "102100",
        "outFields":      out_fields,
        "returnGeometry": "false",
        "spatialRel":     "esriSpatialRelIntersects",
        "where":          "1=1",
    }


def _envelope_params(lat: float, lon: float, out_fields: str, buf: int) -> dict:
    """Build ArcGIS envelope query params."""
    x, y = _to_web_mercator(lat, lon)
    env = {
        "xmin": x - buf, "ymin": y - buf,
        "xmax": x + buf, "ymax": y + buf,
        "spatialReference": {"wkid": 102100},
    }
    return {
        "geometry":          env,
        "geometryType":      "esriGeometryEnvelope",
        "inSR":              "102100",
        "outFields":         out_fields,
        "returnGeometry":    "false",
        "spatialRel":        "esriSpatialRelIntersects",
        "where":             "1=1",
        "resultRecordCount": "50",
        "orderByFields":     "MEASUREDAREA DESC",
    }


def get_district_name(lat: float, lon: float, client: httpx.Client) -> Optional[str]:
    """Return the official Arabic district name for a lat/lon point."""
    data = _query(_ADMIN, 0, _point_params(lat, lon, "DISTRICTNAME_AR"), client)
    feats = (data or {}).get("features", [])
    return feats[0]["attributes"].get("DISTRICTNAME_AR") if feats else None


def get_city_info(lat: float, lon: float, client: httpx.Client) -> dict:
    """Return city name and MOJ city ID for a lat/lon point."""
    data = _query(_ADMIN, 2, _point_params(lat, lon, "CITYNAME_AR,MOJ_CITYID"), client)
    feats = (data or {}).get("features", [])
    if feats:
        attrs = feats[0]["attributes"]
        return {"city_ar": attrs.get("CITYNAME_AR"), "moj_city_id": attrs.get("MOJ_CITYID")}
    return {}


def get_parcel_zoning(lat: float, lon: float,
                      client: httpx.Client,
                      buffer_m: int = _ENVELOPE_BUFFER_M) -> Optional[dict]:
    """
    Return zoning data for the land parcel closest to (lat, lon).

    Uses an envelope query (100 m buffer) because exact-point queries miss
    parcel polygons when the point falls on a boundary or gap.
    Returns the parcel with the largest area within the buffer.

    Returns dict with:
      land_use_ar     : Arabic land-use label  (e.g. "سكني")
      land_use_code   : numeric MAINLANDUSE code
      max_floors      : int or None
      height_cond     : str or None  (special height restriction note)
      measured_area_m2: float or None
      is_commercial   : bool or None
      parcel_status   : int  (0 = active)
      source          : "balady"
    """
    x, y = _to_web_mercator(lat, lon)
    envelope = {
        "xmin": x - buffer_m, "ymin": y - buffer_m,
        "xmax": x + buffer_m, "ymax": y + buffer_m,
        "spatialReference": {"wkid": 102100},
    }
    out_fields = ("MAINLANDUSE,MAINLANDUSEDESCRIPTION,NOOFFLOORS,"
                  "HEIGHTCONDITION,MEASUREDAREA,ISCOMMERCIAL,PARCELSTATUS")
    params = _envelope_params(lat, lon, out_fields, buffer_m)
    data   = _query(_PARCEL, 28, params, client)
    if not data:
        return None

    features = data.get("features", [])
    if not features:
        # Retry with a larger buffer (sparse / rural areas)
        if buffer_m < 500:
            return get_parcel_zoning(lat, lon, client, buffer_m=500)
        return None

    # Pick the feature with highest MAINLANDUSE != null (most informative)
    best = None
    for feat in features:
        a = feat["attributes"]
        if a.get("MAINLANDUSE") and a.get("PARCELSTATUS") == 0:
            best = a
            break
    if best is None:
        best = features[0]["attributes"]

    code = best.get("MAINLANDUSE")
    # Prefer API description; fall back to our static code map
    land_use_ar = (best.get("MAINLANDUSEDESCRIPTION")
                   or _LANDUSE_CODES.get(code)
                   or "غير محدد")

    floors = best.get("NOOFFLOORS")
    # Treat 0 as "not recorded" (API quirk)
    floors = int(floors) if floors and int(floors) > 0 else None

    return {
        "land_use_ar":      land_use_ar,
        "land_use_code":    code,
        "max_floors":       floors,
        "height_cond":      best.get("HEIGHTCONDITION"),
        "measured_area_m2": best.get("MEASUREDAREA"),
        "is_commercial":    bool(best.get("ISCOMMERCIAL")) if best.get("ISCOMMERCIAL") is not None else None,
        "parcel_status":    best.get("PARCELSTATUS", 0),
        "source":           "balady",
    }


# ── Main public API ───────────────────────────────────────────────────────────

def get_zoning_regulations(lat: float, lon: float,
                            district_name: str = "") -> dict:
    """
    High-level entry point: fetch all Balady GIS data for a property.

    Args:
        lat, lon:       WGS-84 coordinates of the property
        district_name:  optional hint (used as fallback if API returns nothing)

    Returns enriched dict with zoning + admin data, is_mock=False if successful.
    """
    result = {
        "source":           "balady",
        "district":         district_name,
        "lat":              lat,
        "lon":              lon,
        "land_use_ar":      None,
        "land_use_code":    None,
        "max_floors":       None,
        "height_cond":      None,
        "measured_area_m2": None,
        "is_commercial":    None,
        "city_ar":          None,
        "moj_city_id":      None,
        "is_mock":          False,
        "error":            None,
    }

    if not lat or not lon:
        result["is_mock"] = True
        result["error"]   = "lat/lon required"
        return result

    try:
        with httpx.Client(headers=_HEADERS, timeout=15, follow_redirects=True) as client:
            # 1. Admin lookups (district + city) in parallel
            district = get_district_name(lat, lon, client) or district_name
            city_info = get_city_info(lat, lon, client)

            # 2. Parcel/zoning data
            zoning = get_parcel_zoning(lat, lon, client)

            result["district"]   = district
            result["city_ar"]    = city_info.get("city_ar")
            result["moj_city_id"] = city_info.get("moj_city_id")

            if zoning:
                result.update(zoning)
            else:
                result["error"] = "no_parcel_data"

    except Exception as e:
        logger.error(f"[balady] get_zoning_regulations error: {e}")
        result["is_mock"] = True
        result["error"]   = str(e)

    return result


# ── Red-flag helper used by pipeline/red_flags.py ─────────────────────────────

def check_zoning_mismatch(listing_usage: str, lat: float, lon: float) -> dict:
    """
    Compare advertised land use (from listing) vs. official Balady zoning.

    Returns:
        { "mismatch": bool, "official": str, "advertised": str, "source": "balady" }
    """
    if not lat or not lon:
        return {"mismatch": False, "official": None, "advertised": listing_usage, "source": "balady"}

    zoning = get_zoning_regulations(lat, lon)
    official = zoning.get("land_use_ar")
    if not official:
        return {"mismatch": False, "official": None, "advertised": listing_usage, "source": "balady"}

    # Simple mismatch: listing says تجاري but official is سكني (or vice versa)
    commercial_terms = {"تجاري", "commercial", "محل", "مكتب", "تجارية"}
    advertised_is_commercial = any(t in (listing_usage or "").lower() for t in commercial_terms)
    official_is_commercial   = "تجاري" in official

    mismatch = advertised_is_commercial != official_is_commercial

    return {
        "mismatch":   mismatch,
        "official":   official,
        "advertised": listing_usage,
        "source":     "balady",
    }


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys, json
    sys.stdout.reconfigure(encoding="utf-8")

    test_cases = [
        {"name": "حي النهضة - الرياض",   "lat": 24.7508, "lon": 46.7917},
        {"name": "King Fahd Road تجاري",  "lat": 24.6936, "lon": 46.6872},
        {"name": "حي الربوة - جدة",       "lat": 21.5822, "lon": 39.1822},
    ]

    for tc in test_cases:
        print(f"\n📍 {tc['name']}")
        result = get_zoning_regulations(tc["lat"], tc["lon"])
        print(f"   المدينة:       {result.get('city_ar')}")
        print(f"   الحي:          {result.get('district')}")
        print(f"   الاستخدام:     {result.get('land_use_ar')} (code={result.get('land_use_code')})")
        print(f"   أقصى أدوار:    {result.get('max_floors')}")
        print(f"   المساحة:       {result.get('measured_area_m2')} م²")
        print(f"   is_mock:       {result.get('is_mock')}  error={result.get('error')}")
        time.sleep(1)
