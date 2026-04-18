"""
CFO Manager Module (Corporate Finance for Real Estate).

Provides advanced financial metrics beyond simple ROI:
- IRR (Internal Rate of Return)
- Cashflow Schedules & Capital Calls
- Wafi (Off-plan) vs Ready sales comparison
- Dynamic construction and financing rates
"""
import numpy_financial as npf
from core.logger import get_logger

logger = get_logger("cfo_manager")

# In the future, this SIBOR will be updated by a SAMA scraper
DYNAMIC_SIBOR_RATE = 0.055  # 5.5% today
BANK_MARGIN = 0.015         # 1.5% fixed bank margin
DYNAMIC_INTEREST_RATE = DYNAMIC_SIBOR_RATE + BANK_MARGIN

def calculate_irr(cashflows: list[float]) -> float:
    """Calculate the Internal Rate of Return (IRR) for a series of cashflows."""
    try:
        irr = npf.irr(cashflows)
        # If no IRR can be found or it's infinite, npf.irr returns nan
        if irr is None or str(irr).lower() == 'nan':
            return 0.0
        return round(irr * 100, 2) # Monthly or period IRR converted below?
        # Actually npf.irr returns the rate per period. If cashflows are monthly,
        # IRR needs to be annualized.
    except Exception as e:
        logger.error(f"Error calculating IRR: {e}")
        return 0.0

def generate_cashflow_schedule(land_cost: float, construction_cost: float, duration_months: int, total_revenue: float) -> dict:
    """
    Simulates a capital call schedule.
    Month 0: Pay land cost + 10% mobilization
    Months 1 to N-1: Pay construction linearly
    Month N: Receive total revenue
    """
    cashflows = []
    
    # Month 0: Land + Mobilization
    mobilization = construction_cost * 0.10
    cashflows.append(-(land_cost + mobilization))
    
    # Months 1 to N-1: Construction
    remaining_construction = construction_cost - mobilization
    monthly_burn = remaining_construction / max(1, (duration_months - 1))
    
    for _ in range(1, duration_months):
        cashflows.append(-monthly_burn)
        
    # Month N: Sale
    cashflows.append(total_revenue)
    
    # Annualize IRR Assuming periods are months
    period_irr = npf.irr(cashflows)
    if period_irr is None or str(period_irr).lower() == 'nan':
        annual_irr = 0.0
    else:
        annual_irr = ((1 + period_irr) ** 12) - 1
        
    return {
        "schedule": [round(c, 2) for c in cashflows],
        "max_equity_required": round(land_cost + construction_cost, 2),
        "annualized_irr_pct": round(annual_irr * 100, 2)
    }

def analyze_wafi_feasibility(land_cost: float, construction_cost: float, total_revenue: float, market_depth_condition: str) -> dict:
    """
    Analyzes whether WAFI (Off-plan) is better than Ready delivery.
    Off-plan means construction is funded by buyers (no out of pocket const. cost).
    However, revenue per sqm is usually 10-15% lower due to off-plan discount.
    """
    
    # If market is oversupplied, Wafi is extremely risky (projects stall if no buyers)
    if market_depth_condition == "OVERSUPPLIED":
        return {
            "recommended": False,
            "reason": "Market is oversupplied. High risk of off-plan sales failing, causing project stall.",
            "wafi_irr_pct": 0,
            "equity_required": land_cost + construction_cost
        }
        
    # Apply Off-Plan Discount (15%)
    wafi_revenue = total_revenue * 0.85
    
    # WAFI Cashflow (Extremely simple model):
    # Year 0: Buy land (-land_cost)
    # Year 1-2: Construction paid by buyers (cashflow 0)
    # Year 2 end: recognize profit (wafi_revenue - construction_cost) => basically Net profit arrives
    
    # Actually, as a developer you get the profit (wafi_revenue - construction) at the end or recognized over time.
    # We will model it as:
    # M0: -land_cost
    # M24: (wafi_revenue - construction_cost) + land_cost (value recycled)
    # Let's just say M24 total net cash received back is the wafi profit + original land principal
    wafi_net_return = wafi_revenue - construction_cost
    
    wafi_cashflows = [-land_cost] + [0]*23 + [wafi_net_return + land_cost]
    period_irr = npf.irr(wafi_cashflows)
    
    if period_irr is None or str(period_irr).lower() == 'nan':
        annual_irr = 0.0
    else:
        annual_irr = (((1 + period_irr) ** 12) - 1) * 100

    return {
        "recommended": annual_irr > 20.0, # Recommend Wafi if IRR > 20%
        "reason": f"Wafi drops capital needs to the land cost only ({land_cost:,.0f} SAR), boosting IRR to {annual_irr:.1f}% despite lower sell price.",
        "wafi_irr_pct": round(annual_irr, 2),
        "equity_required": round(land_cost, 2),
        "expected_revenue": round(wafi_revenue, 2)
    }
