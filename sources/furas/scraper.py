"""
منصة فرص (Furas) Mock Scraper
TODO: سيتم برمجتها لاحقاً لسحب الفرص الاستثمارية البلدية المطروحة بجوار العقار المستهدف.
"""
from typing import Dict

def get_nearby_municipal_investments(lat: float, lon: float, radius_km: float = 2.0) -> Dict:
    """
    يجلب الاستثمارات البلدية القريبة (حدائق، أسواق نفع عام، مسالخ، إلخ).
    # Mock Data
    """
    return {
        "source": "furas",
        "active_opportunities_nearby": 3,
        "opportunities": [
            {"type": "Commercial Park", "distance_km": 0.5, "status": "Awarded"},
            {"type": "Public Parking", "distance_km": 1.2, "status": "Tendering"}
        ],
        "competitive_impact": "Positive", # تأثير إيجابي على قيمة العقار
        "is_mock": True
    }
