"""
Financial analysis for land opportunities.

Provides:
  - calculate_roi(): Single expected-case ROI (backward compatible)
  - calculate_roi_scenarios(): 3 scenarios (optimistic/expected/pessimistic)
  - Full hidden costs + optional financing integration

Uses price benchmarks when available (30% development markup over market avg),
falls back to hardcoded SELL_PRICE from config.py when benchmark data is thin.
"""
from config import CONSTRUCTION_COST, SELL_PRICE, UNIT_SIZE_SQM
from pipeline.benchmarks import get_benchmark
from pipeline.hidden_costs import calculate_hidden_costs, calculate_financing
from pipeline.zoning import get_zoning_rules


def _base_roi_inputs(analysis: dict) -> dict:
    """Extract and normalise shared inputs for all ROI calculations."""
    land_price = float(analysis.get("asking_price_sar") or 0)
    area_sqm = float(analysis.get("land_area_sqm") or 0)
    dev_type = (analysis.get("recommended_development") or "apartments").lower()
    location = analysis.get("location") or ""
    city = location.split("/")[0].strip()
    district = location.split("/")[-1].strip() if "/" in location else ""

    if dev_type not in CONSTRUCTION_COST:
        dev_type = "apartments"

    zoning = get_zoning_rules(city, district)
    
    if dev_type in ["apartments", "mixed", "commercial"]:
        far = zoning["far"]
    else:
        # Villas generally have different FAR constraints (~1.2 - 1.5 max)
        from config import FAR as CONFIG_FAR
        far = CONFIG_FAR.get("villas", 1.2)

    buildable_sqm = area_sqm * far
    cost_per_sqm = CONSTRUCTION_COST.get(dev_type, 2500)

    bench = get_benchmark(city, district) or get_benchmark(city, "")
    if bench and bench["count"] >= 5:
        sell_per_sqm = bench["avg"] * 1.30   # 30% development markup
        benchmark_source = "district" if district else "city"
    else:
        sell_per_sqm = SELL_PRICE.get(dev_type, 6500)
        benchmark_source = "hardcoded"

    return {
        "land_price": land_price,
        "area_sqm": area_sqm,
        "dev_type": dev_type,
        "city": city,
        "district": district,
        "far": far,
        "buildable_sqm": buildable_sqm,
        "cost_per_sqm": cost_per_sqm,
        "sell_per_sqm": sell_per_sqm,
        "benchmark_source": benchmark_source,
        "bench": bench,
    }


def _compute_scenario(
    land_price: float,
    buildable_sqm: float,
    cost_per_sqm: float,
    sell_per_sqm: float,
    dev_type: str,
    timeline_months: int,
    include_hidden: bool = True,
) -> dict:
    """Compute a single ROI scenario with optional hidden costs."""
    build_cost = buildable_sqm * cost_per_sqm
    total_base = land_price + build_cost
    projected_revenue = buildable_sqm * sell_per_sqm

    if include_hidden:
        hidden = calculate_hidden_costs(
            land_price, build_cost,
            projected_revenue=projected_revenue,
        )
        total_investment = total_base + hidden["total_hidden_costs"]
    else:
        hidden = {"total_hidden_costs": 0}
        total_investment = total_base

    gross_profit = projected_revenue - total_investment
    roi = (gross_profit / total_investment * 100) if total_investment > 0 else 0

    return {
        "land_cost_sar": land_price,
        "build_cost_sar": round(build_cost),
        "hidden_costs_sar": hidden["total_hidden_costs"],
        "total_investment_sar": round(total_investment),
        "total_revenue_sar": round(projected_revenue),
        "gross_profit_sar": round(gross_profit),
        "roi_pct": round(roi, 1),
        "timeline_months": timeline_months,
        "buildable_bua_sqm": buildable_sqm,
    }


def calculate_roi(analysis: dict) -> dict:
    """Calculate EXPECTED-case ROI (backward compatible).

    Now includes hidden costs by default for more realistic numbers.
    """
    inp = _base_roi_inputs(analysis)

    timeline = 24 if inp["dev_type"] in ["apartments", "mixed"] else 12

    result = _compute_scenario(
        inp["land_price"], inp["buildable_sqm"],
        inp["cost_per_sqm"], inp["sell_per_sqm"],
        inp["dev_type"], timeline,
        include_hidden=True,
    )

    result["benchmark_source"] = inp["benchmark_source"]
    result["benchmark_avg_sqm"] = inp["bench"]["avg"] if inp["bench"] else None

    # Also compute breakeven for reference
    if inp["buildable_sqm"] > 0 and result["total_investment_sar"] > 0:
        result["breakeven_sell_sqm"] = round(
            result["total_investment_sar"] / inp["buildable_sqm"]
        )
    else:
        result["breakeven_sell_sqm"] = 0

    return result


def calculate_roi_scenarios(analysis: dict) -> dict:
    """Calculate 3 scenarios: optimistic, expected, pessimistic.

    Returns a dict with keys: optimistic, expected, pessimistic, breakeven, financing.
    """
    inp = _base_roi_inputs(analysis)

    base_timeline = 24 if inp["dev_type"] in ["apartments", "mixed"] else 12

    # ── Optimistic: costs as-is, sell +10%, timeline -3 months ─────────────────
    optimistic = _compute_scenario(
        inp["land_price"], inp["buildable_sqm"],
        inp["cost_per_sqm"],
        inp["sell_per_sqm"] * 1.10,    # 10% better sale price
        inp["dev_type"],
        max(base_timeline - 3, 6),
        include_hidden=True,
    )

    # ── Expected: costs as-is, sell as-is ──────────────────────────────────────
    expected = _compute_scenario(
        inp["land_price"], inp["buildable_sqm"],
        inp["cost_per_sqm"],
        inp["sell_per_sqm"],
        inp["dev_type"],
        base_timeline,
        include_hidden=True,
    )

    # ── Pessimistic: costs +20%, sell -15%, timeline +50% ──────────────────────
    pessimistic = _compute_scenario(
        inp["land_price"], inp["buildable_sqm"],
        inp["cost_per_sqm"] * 1.20,    # 20% cost overrun
        inp["sell_per_sqm"] * 0.85,    # 15% lower sale price
        inp["dev_type"],
        int(base_timeline * 1.5),
        include_hidden=True,
    )

    # ── Breakeven: minimum sell price per m² to not lose money ─────────────────
    if inp["buildable_sqm"] > 0:
        breakeven_sell_sqm = round(expected["total_investment_sar"] / inp["buildable_sqm"])
    else:
        breakeven_sell_sqm = 0

    # ── Financing: what if 70% financed at 7% for 5 years ─────────────────────
    financing = calculate_financing(
        expected["total_investment_sar"],
        financing_pct=0.70,
        annual_rate=0.07,
        years=5,
    )

    # Effective ROI after financing costs = return ON EQUITY (not on total debt)
    # Numerator: revenue minus all costs including principal + interest repayment
    # Denominator: equity_needed (the cash the investor actually puts in)
    if financing["equity_needed"] > 0:
        effective_profit = expected["total_revenue_sar"] - financing["total_with_financing"]
        financing["effective_roi_pct"] = round(
            effective_profit / financing["equity_needed"] * 100, 1
        )
    else:
        financing["effective_roi_pct"] = 0

    return {
        "optimistic": optimistic,
        "expected": expected,
        "pessimistic": pessimistic,
        "breakeven_sell_sqm": breakeven_sell_sqm,
        "financing": financing,
        "benchmark_source": inp["benchmark_source"],
        "benchmark_avg_sqm": inp["bench"]["avg"] if inp["bench"] else None,
        # Convenience flag for the pipeline
        "pessimistic_loss": pessimistic["roi_pct"] < 0,
    }
