"""
البنك المركزي السعودي (SAMA) Mock Scraper
TODO: سيتم برمجتها لاحقاً للحصول على بيانات السايبور (SAIBOR) / أسعار الفائدة لتكاليف التمويل.
"""
from typing import Dict

def get_financing_rates() -> Dict:
    """
    يجلب نسبة SAIBOR لتوظيفها في العمليات المالية (cfo_manager) لاحتساب تكلفة رأس المال (WACC).
    # Mock Data
    """
    return {
        "source": "sama",
        "saibor_3_months": 0.058, # السايبور لـ 3 أشهر: 5.8%
        "saibor_6_months": 0.061,
        "mortgage_origination_trend": "Stable",
        "inflation_rate": 0.016, # التضخم 1.6%
        "is_mock": True
    }
