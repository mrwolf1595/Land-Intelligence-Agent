"""
Rule-based logic for testing ROI of a land opportunity.
"""
from config import CONSTRUCTION_COST, SELL_PRICE, FAR, UNIT_SIZE_SQM

def calculate_roi(analysis: dict) -> dict:
    land_price = float(analysis.get("asking_price_sar", 0))
    area_sqm = float(analysis.get("land_area_sqm", 0) or 0)
    dev_type = analysis.get("recommended_development", "apartments").lower()
    
    if dev_type not in CONSTRUCTION_COST:
        dev_type = "apartments"

    far = FAR.get(dev_type, 2.0)
    buildable_sqm = area_sqm * far
    
    cost_per_sqm = CONSTRUCTION_COST.get(dev_type, 2500)
    sell_per_sqm = SELL_PRICE.get(dev_type, 6500)
    
    build_cost = buildable_sqm * cost_per_sqm
    total_investment = land_price + build_cost
    
    projected_revenue = buildable_sqm * sell_per_sqm
    gross_profit = projected_revenue - total_investment
    
    if total_investment > 0:
        roi = (gross_profit / total_investment) * 100
    else:
        roi = 0

    return {
        "land_cost_sar": land_price,
        "build_cost_sar": build_cost,
        "total_investment_sar": total_investment,
        "total_revenue_sar": projected_revenue,
        "gross_profit_sar": gross_profit,
        "roi_pct": round(roi, 1),
        "timeline_months": 24 if dev_type in ["apartments", "mixed"] else 12,
        "buildable_bua_sqm": buildable_sqm
    }
