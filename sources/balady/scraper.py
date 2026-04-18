"""
منصة بلدي (Balady) Mock Scraper
TODO: سيتم برمجتها لاحقاً للتحقق من كود البناء السعودي ونسبة البناء والاستخدامات المسموحة.
"""
from typing import Dict

def get_zoning_regulations(lat: float, lon: float, district_name: str) -> Dict:
    """
    يجلب الاشتراطات البلدية وكود البناء للقطعة المستهدفة.
    # Mock Data
    """
    return {
        "source": "balady",
        "district": district_name,
        "zoning_code": "C3", # تجاري
        "allowed_usage": ["Retail", "Offices", "Hospitality"],
        "max_building_ratio": 0.60, # نسبة البناء 60%
        "max_floors": 4, # الحد الأقصى للأدوار
        "setbacks": {"front": 3, "sides": 2, "back": 2}, # الارتدادات
        "is_mock": True
    }
