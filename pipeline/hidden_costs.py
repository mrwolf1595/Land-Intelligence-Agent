"""
Hidden costs calculator for Saudi real estate transactions.

Accounts for all the fees and taxes that the basic ROI calculation misses:
  - ضريبة التصرفات العقارية (5% Real Estate Transaction Tax)
  - رسوم البلدية (Municipality fees)
  - تسويق (Marketing costs)
  - رسوم قانونية (Legal/notary fees)
  - احتياطي طوارئ (Contingency reserve)
  - تكلفة التمويل (Financing costs, if applicable)
"""


# ── Saudi-specific constants ──────────────────────────────────────────────────
RETT_PCT = 0.05           # Real Estate Transaction Tax (ضريبة التصرفات العقارية)
MUNICIPALITY_FEES = 15_000  # Approximate building permit + municipality fees
MARKETING_PCT = 0.03      # 3% marketing/brokerage to sell the finished product
LEGAL_FEES = 8_000        # Lawyer, notary, contract drafting
CONTINGENCY_PCT = 0.10    # 10% contingency on construction cost
INFRASTRUCTURE_PCT = 0.05 # 5% for utilities connection, landscaping, etc.


def calculate_hidden_costs(
    land_price: float,
    build_cost: float,
    include_buy_tax: bool = True,
    include_sell_tax: bool = True,
    projected_revenue: float = 0.0,
) -> dict:
    """Calculate all hidden costs that the basic ROI misses.

    Args:
        land_price: Purchase price of the land (SAR).
        build_cost: Total construction cost (SAR).
        include_buy_tax: Include 5% RETT on land purchase.
        include_sell_tax: Include 5% RETT on selling completed units.
        projected_revenue: Expected total sale revenue (for sell-side tax).

    Returns:
        dict with itemized costs and total.
    """
    buy_tax = land_price * RETT_PCT if include_buy_tax else 0.0
    sell_tax = projected_revenue * RETT_PCT if include_sell_tax and projected_revenue > 0 else 0.0
    marketing = projected_revenue * MARKETING_PCT if projected_revenue > 0 else (land_price + build_cost) * MARKETING_PCT
    contingency = build_cost * CONTINGENCY_PCT
    infrastructure = build_cost * INFRASTRUCTURE_PCT

    total = buy_tax + sell_tax + MUNICIPALITY_FEES + marketing + LEGAL_FEES + contingency + infrastructure

    return {
        "buy_transfer_tax": round(buy_tax),
        "sell_transfer_tax": round(sell_tax),
        "municipality_fees": MUNICIPALITY_FEES,
        "marketing_cost": round(marketing),
        "legal_fees": LEGAL_FEES,
        "contingency": round(contingency),
        "infrastructure": round(infrastructure),
        "total_hidden_costs": round(total),
        "breakdown_note_ar": (
            f"ضريبة شراء {RETT_PCT*100:.0f}%: {buy_tax:,.0f} | "
            f"ضريبة بيع: {sell_tax:,.0f} | "
            f"بلدية: {MUNICIPALITY_FEES:,} | "
            f"تسويق: {marketing:,.0f} | "
            f"طوارئ: {contingency:,.0f} | "
            f"بنية تحتية: {infrastructure:,.0f}"
        ),
    }


def calculate_financing(
    total_investment: float,
    financing_pct: float = 0.70,
    annual_rate: float = 0.07,
    years: int = 5,
) -> dict:
    """Calculate cost of bank financing.

    Args:
        total_investment: Total project cost (land + build + hidden).
        financing_pct: What fraction is financed (0.0-1.0).
        annual_rate: Annual profit rate (Saudi banks: ~6-8%).
        years: Loan term in years.

    Returns:
        dict with equity needed, monthly payment, total interest cost.
    """
    if financing_pct <= 0 or total_investment <= 0:
        return {
            "equity_needed": total_investment,
            "loan_amount": 0,
            "total_interest": 0,
            "monthly_payment": 0,
            "total_with_financing": total_investment,
            "financing_pct": 0,
        }

    loan = total_investment * financing_pct
    equity = total_investment * (1 - financing_pct)
    total_interest = loan * annual_rate * years
    total_with_financing = total_investment + total_interest
    monthly_payment = (loan + total_interest) / (years * 12)

    return {
        "equity_needed": round(equity),
        "loan_amount": round(loan),
        "total_interest": round(total_interest),
        "monthly_payment": round(monthly_payment),
        "total_with_financing": round(total_with_financing),
        "financing_pct": financing_pct,
        "annual_rate": annual_rate,
        "years": years,
    }
