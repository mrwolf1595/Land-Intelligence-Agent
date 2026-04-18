"""
Smart Alerts System.

Prevents spamming the broker with "okay" opportunities.
Only sends WhatsApp alerts if a strict set of rules are met:
- HOT_DEAL: Score >= 8, High Confidence, and Pessimistic ROI > 15%
- NO_LOSS_DEAL: Score >= 7, Market is NOT oversaturated, Negative Red Flags = 0

If it doesn't meet these criteria, it stays in the DB/Dashboard but doesn't ding the phone.
"""

from core.logger import get_logger

logger = get_logger("smart_alerts")

def evaluate_smart_alert(analysis: dict, financial: dict) -> tuple[bool, str]:
    """
    Evaluate whether to send a push notification.
    Returns (should_send: bool, alert_type: str)
    """
    score = analysis.get("opportunity_score", 0)
    confidence = analysis.get("confidence", "LOW")
    red_flags = analysis.get("red_flags", [])
    
    # Check if any HIGH severity flags
    if any(f.get("severity") == "HIGH" for f in red_flags):
        return False, "BLOCKING_FLAGS"
        
    scenarios = financial.get("scenarios", {})
    if not scenarios:
        # Fallback if scenarios weren't calculated for some reason
        roi = financial.get("roi_pct", 0)
        if score >= 8 and roi > 25:
            return True, "🔥 فرصة ممتازة (Basic)"
        return False, "BELOW_THRESHOLD"

    pes_roi = scenarios.get("pessimistic", {}).get("roi_pct", 0)
    exp_roi = scenarios.get("expected", {}).get("roi_pct", 0)
    
    # ── Rule 1: HOT DEAL ──────────────────────────────────────────────────────
    # Exceptionally good score, high confidence, and profitable even in worst case
    if score >= 8.0 and confidence in ["HIGH", "MEDIUM"] and pes_roi >= 10.0:
        return True, "🔥 صفقة استثنائية (آمنة من الخسارة)"
        
    # ── Rule 2: SOLID DEAL ────────────────────────────────────────────────────
    # Good score, no red flags, expected returns are > 25%
    if score >= 7.5 and not red_flags and exp_roi > 25.0 and pes_roi >= 0:
        return True, "💡 فرصة ممتازة (قليلة المخاطر)"
        
    # ── Rule 3: MARKET DISCOUNT ───────────────────────────────────────────────
    # It is significantly cheaper than the market even if area is small
    # Score gets bumped if price << market.
    if score >= 8.5:
        return True, "📉 سعر أقل من السوق بكثير"

    # Otherwise, it's just recorded in DB for dashboard review
    return False, "SILENT_DB_ONLY"
