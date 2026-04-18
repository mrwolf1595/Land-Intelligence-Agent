"""
المركز الوطني للمعلومات الجيومكانية (GASGI) Mock Scraper
TODO: سيتم برمجتها لاحقاً للتحقق من مناطق نزع الملكيات، مسارات السيول، والمخططات الهيكلية.
"""
from typing import Dict

def get_geospatial_hazards(lat: float, lon: float) -> Dict:
    """
    يتحقق مما إذا كانت الإحداثيات تقع في منطقة نزع ملكية أو منطقة مجاري سيول أو أودية.
    # Mock Data
    """
    return {
        "source": "gasgi",
        "in_expropriation_zone": False, # ليست ضمن مناطق النزع
        "in_flood_plain": False, # ليست في مجرى سيول
        "nearest_mega_project": "Qiddiya",
        "distance_to_mega_project_km": 15.5,
        "is_mock": True
    }
