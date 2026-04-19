"""
Sends match notifications to the BROKER (you) via WhatsApp Node Bridge.
"""
import httpx
from config import WA_BRIDGE_PORT, BROKER_WHATSAPP
from core.logger import get_logger

logger = get_logger("notifier")

WA_BRIDGE_URL = f"http://localhost:{WA_BRIDGE_PORT}"

def format_match_message(match: dict) -> str:
    score_pct = int(match.get("match_score", 0) * 100)
    score_emoji = "🟢" if score_pct >= 80 else "🟡" if score_pct >= 65 else "🟠"

    msg = f"""🏠 *تطابق عقاري جديد* {score_emoji} {score_pct}%
━━━━━━━━━━━━━━━━━━━━

📋 *الطالب:*
• الاسم: {match.get('req_name', 'غير محدد')}
• المجموعة: {match.get('req_group', '')}
• الطلب: {match.get('req_text', '')[:200]}
• المدينة: {match.get('req_city', 'غير محددة')}
• السعر: {_fmt_price(match.get('req_price'))}
━━━━━━━━━━━━━━━━━━━━

🏗️ *العارض:*
• الاسم: {match.get('off_name', 'غير محدد')}
• المجموعة: {match.get('off_group', '')}
• العرض: {match.get('off_text', '')[:200]}
• المدينة: {match.get('off_city', 'غير محددة')}
• السعر: {_fmt_price(match.get('off_price'))}
━━━━━━━━━━━━━━━━━━━━

🤝 *سبب التطابق:*
{match.get('match_reasoning', '')}

💡 *نصيحة:*
{match.get('broker_tip', '')}

🆔 Match ID: {match.get('match_id', '')[:8]}"""

    return msg

def notify_broker_match(match: dict) -> bool:
    message = format_match_message(match)
    return _send_whatsapp(BROKER_WHATSAPP, message)

def notify_broker_opportunity(analysis: dict, financial: dict, pdf_path: str = None) -> bool:
    # Use expected scenario if available, fallback to old format
    scenarios = financial.get("scenarios")
    if scenarios:
        expected = scenarios.get("expected", {})
        roi = expected.get("roi_pct", 0)
        total_inv = expected.get("total_investment_sar", 0)
        total_rev = expected.get("total_revenue_sar", 0)
        profit = expected.get("gross_profit_sar", 0)
        timeline = expected.get("timeline_months", "?")
        hidden = expected.get("hidden_costs_sar", 0)
        pes_roi = scenarios.get("pessimistic", {}).get("roi_pct", 0)
    else:
        roi = financial.get("roi_pct", 0)
        total_inv = financial.get("total_investment_sar", 0)
        total_rev = financial.get("total_revenue_sar", 0)
        profit = financial.get("gross_profit_sar", 0)
        timeline = financial.get("timeline_months", "?")
        hidden = 0
        pes_roi = 0

    score = analysis.get("opportunity_score", 0)
    bench_source = _bench_source_label(analysis.get("benchmark_source"))
    bench_count = analysis.get("benchmark_sample_count")
    bench_as_of = analysis.get("benchmark_as_of")
    
    red_flags = analysis.get("red_flags", [])
    flags_msg = ""
    if red_flags:
        flags_msg = f"\n⚠️ *ملاحظات تحذيرية:* {len(red_flags)} ملاحظة"

    smart_alert_reason = analysis.get("smart_alert_reason", "")
    alert_header = f"🚨 *تنبيه ذكي: {smart_alert_reason}*" if smart_alert_reason else "🏗️ *فرصة عقارية عالية القيمة*"

    msg = f"""{alert_header}
━━━━━━━━━━━━━━━━━━━━

📍 الموقع: {analysis.get('location', 'غير محدد')}
📐 المساحة: {analysis.get('land_area_sqm', '?')} م²
💰 السعر: {_fmt_price(analysis.get('asking_price_sar'))}
🏆 درجة الفرصة: {score}/10{flags_msg}
🏢 التطوير المقترح: {_dev_label(analysis.get('recommended_development'))}

📚 *مرجعية التسعير:*
• المصدر: {bench_source}
• حجم العينة: {bench_count if bench_count else 'غير متاح'}
• آخر تحديث: {bench_as_of if bench_as_of else 'غير متاح'}

💹 *النموذج المالي (السيناريو المتوقع):*
• إجمالي الاستثمار (مع الرسوم المخفية): {_fmt_price(total_inv)}
• الرسوم المخفية: {_fmt_price(hidden)}
• الإيرادات المتوقعة: {_fmt_price(total_rev)}
• صافي الربح: {_fmt_price(profit)}
• العائد المتوقع: {roi}% خلال {timeline} شهر
• عائد السيناريو المتشائم: {pes_roi}%

🔗 {analysis.get('source_url', '')}
{"📎 تم إرفاق الـ Proposal PDF" if pdf_path else ""}"""

    return _send_whatsapp(BROKER_WHATSAPP, msg)

def _send_whatsapp(to: str, message: str) -> bool:
    if not to:
        logger.error("BROKER_WHATSAPP not set in .env — cannot send notification")
        return False
    try:
        r = httpx.post(
            f"{WA_BRIDGE_URL}/send",
            json={"to": to, "message": message},
            timeout=10
        )
        if r.status_code == 200 and r.json().get('success'):
            return True
        logger.warning(f"WhatsApp send returned status {r.status_code}")
        return False
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return False

def _fmt_price(price) -> str:
    if not price:
        return "غير محدد"
    try:
        return f"{int(price):,} ر.س"
    except:
        return f"{price} ر.س"

def _dev_label(dev_type: str) -> str:
    mapping = {
        "apartments": "عمارة شقق",
        "villas": "فلل مستقلة",
        "commercial": "تجاري",
        "mixed": "متعدد الاستخدامات"
    }
    return mapping.get(str(dev_type).lower(), "غير محدد")


def _bench_source_label(source: str | None) -> str:
    mapping = {
        "moj": "وزارة العدل (MOJ) — صفقات فعلية",
        "local_moj": "MOJ محلي (CSV) — صفقات فعلية",
        "scraped": "منصات إعلانية (Scraped) — عروض وليس صفقات",
    }
    return mapping.get((source or "").lower(), "غير متاح")
