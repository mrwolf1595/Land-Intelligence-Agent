"""
برنامج وافي (Wafi) Mock Scraper
TODO: سيتم برمجتها لاحقاً لجلب بيانات المعروض القادم ومشاريع البيع على الخارطة.
"""
from typing import Dict

def get_supply_pipeline(district_name: str) -> Dict:
    """
    يجلب حجم مشاريع البيع على الخارطة المعتمدة في الحي لتوقع وفرة المعروض (Supply).
    # Mock Data
    """
    return {
        "source": "wafi",
        "district": district_name,
        "upcoming_units": 450, # وحدات قادمة خلال 3 سنوات
        "mega_projects_count": 2, # عدد مشاريع التطوير الشامل
        "absorption_risk": "Medium", # مخاطر تشبع السوق
        "is_mock": True
    }
