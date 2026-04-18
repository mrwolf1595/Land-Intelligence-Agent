"""
Red Flags Engine — detects suspicious listings that could cause financial loss.

Checks:
  - Suspiciously low price (< 50% of market benchmark)
  - No deed (صك) or plot number mentioned
  - Urgency/scam language patterns
  - No contact info
  - Vague or missing location
  - Unrealistic area
  - Price outside rational bounds
"""

import re
from dataclasses import dataclass, field
from pipeline.benchmarks import get_benchmark
from core.logger import get_logger

# Balady zoning check — lazy import to avoid startup cost
def _balady_zoning_check(listing: dict) -> dict | None:
    """Try Balady GIS zoning check. Returns result or None if unavailable/slow."""
    lat = listing.get("lat") or listing.get("latitude")
    lon = listing.get("lon") or listing.get("longitude")
    if not lat or not lon:
        return None
    try:
        from sources.balady.scraper import check_zoning_mismatch
        advertised = listing.get("property_type") or listing.get("type_ar") or ""
        return check_zoning_mismatch(advertised, float(lat), float(lon))
    except Exception as e:
        logger.debug(f"[red_flags] Balady check skipped: {e}")
        return None

logger = get_logger("red_flags")


@dataclass
class RedFlag:
    code: str
    severity: str          # "HIGH", "MEDIUM", "LOW"
    message_ar: str        # Arabic description for broker
    message_en: str = ""   # English (for logs/debug)


def detect_red_flags(listing: dict, bench: dict | None = None) -> list[RedFlag]:
    """Scan a listing for red flags. Returns list (empty = no concerns)."""
    flags: list[RedFlag] = []

    price_sar = float(listing.get("price_sar") or 0)
    area_sqm  = float(listing.get("area_sqm") or 0)
    city      = listing.get("city", "")
    district  = listing.get("district", "")
    body      = listing.get("raw_text", "") or listing.get("bodyTEXT", "") or ""
    title     = listing.get("title", "") or ""
    phone     = listing.get("contact_phone", "")
    full_text = f"{title} {body}".strip()

    price_sqm = price_sar / area_sqm if area_sqm > 0 and price_sar > 0 else 0

    # ── Get benchmark if not provided ────────────────────────────────────────
    if bench is None and city:
        bench = get_benchmark(city, district) or get_benchmark(city, "")

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. PRICE RED FLAGS
    # ═══════════════════════════════════════════════════════════════════════════

    if bench and bench["count"] >= 3 and price_sqm > 0:
        ratio = price_sqm / bench["avg"]

        if ratio < 0.40:
            flags.append(RedFlag(
                "PRICE_EXTREMELY_LOW", "HIGH",
                f"⛔ السعر أقل من 40% من متوسط السوق — احتمال كبير وجود مشاكل قانونية أو نزاع",
                f"Price {ratio:.0%} of market avg ({bench['avg']:,.0f}/m²)",
            ))
        elif ratio < 0.55:
            flags.append(RedFlag(
                "PRICE_SUSPICIOUSLY_LOW", "HIGH",
                f"🚨 السعر أقل من نصف سعر السوق — تحقق من وجود نزاع أو مشاكل في الصك",
                f"Price {ratio:.0%} of market avg",
            ))
        elif ratio > 2.0:
            flags.append(RedFlag(
                "PRICE_EXTREMELY_HIGH", "MEDIUM",
                f"💸 السعر أعلى من ضعف المتوسط — تأكد من المصدر وقارن بالمنطقة",
                f"Price {ratio:.0%} of market avg",
            ))

    # Price = 0 or missing
    if price_sar <= 0:
        flags.append(RedFlag(
            "NO_PRICE", "MEDIUM",
            "❓ السعر غير محدد — اطلبه قبل أي خطوة",
            "No price listed",
        ))

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. LEGAL / DEED RED FLAGS
    # ═══════════════════════════════════════════════════════════════════════════

    deed_keywords = ["صك", "رقم القطعة", "المخطط", "صك إلكتروني", "إفراغ", "ناجز"]
    has_deed_mention = any(kw in full_text for kw in deed_keywords)

    if not has_deed_mention and len(full_text) > 50:
        flags.append(RedFlag(
            "NO_DEED_MENTIONED", "MEDIUM",
            "📋 لم يُذكر رقم الصك أو المخطط — تأكد من وجود صك إلكتروني صالح",
            "No deed/plot number in text",
        ))

    # Explicit risk phrases
    risk_phrases = [
        ("نزاع", "DISPUTE_MENTIONED", "HIGH", "⚠️ مذكور في الإعلان وجود نزاع"),
        ("مشكلة", "PROBLEM_MENTIONED", "MEDIUM", "⚠️ كلمة 'مشكلة' مذكورة — اقرأ بعناية"),
        ("إيقاف", "HOLD_MENTIONED", "HIGH", "🛑 مذكور إيقاف على العقار"),
        ("رهن", "MORTGAGE_MENTIONED", "MEDIUM", "🏦 العقار عليه رهن — تأكد من فكه قبل الشراء"),
        ("وكالة", "POWER_OF_ATTORNEY", "MEDIUM", "📝 البيع عن طريق وكالة — تحقق من الوكالة الشرعية"),
    ]
    for phrase, code, severity, msg in risk_phrases:
        if phrase in full_text:
            flags.append(RedFlag(code, severity, msg))

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. SCAM / URGENCY PATTERNS
    # ═══════════════════════════════════════════════════════════════════════════

    urgency_phrases = ["عاجل", "فرصة لا تتكرر", "البيع اليوم", "آخر فرصة", "أقل من التكلفة"]
    urgency_count = sum(1 for p in urgency_phrases if p in full_text)

    if urgency_count >= 2 and bench and price_sqm > 0 and (price_sqm / bench["avg"]) < 0.70:
        flags.append(RedFlag(
            "URGENCY_PLUS_LOW_PRICE", "HIGH",
            "🚩 استعجال + سعر منخفض جداً = علامات احتيال محتملة",
            f"Urgency phrases ({urgency_count}) + below-market price",
        ))
    elif urgency_count >= 2:
        flags.append(RedFlag(
            "EXCESSIVE_URGENCY", "LOW",
            "⏰ لغة استعجال مبالغ فيها — خذ وقتك في التحقق",
            f"{urgency_count} urgency phrases found",
        ))

    # ═══════════════════════════════════════════════════════════════════════════
    # 4. CONTACT / SELLER RED FLAGS
    # ═══════════════════════════════════════════════════════════════════════════

    if not phone and len(full_text) > 30:
        flags.append(RedFlag(
            "NO_CONTACT", "LOW",
            "📵 لا يوجد رقم تواصل واضح",
            "No phone number found",
        ))

    # ═══════════════════════════════════════════════════════════════════════════
    # 5. LOCATION RED FLAGS
    # ═══════════════════════════════════════════════════════════════════════════

    if not city or city == "غير محدد":
        flags.append(RedFlag(
            "NO_CITY", "MEDIUM",
            "📍 المدينة غير محددة — لا يمكن التقييم بدون موقع",
            "City not specified",
        ))

    if not district and city:
        flags.append(RedFlag(
            "NO_DISTRICT", "LOW",
            "📍 الحي غير محدد — التقييم أقل دقة",
            "District not specified",
        ))

    # ═══════════════════════════════════════════════════════════════════════════
    # 6. AREA RED FLAGS
    # ═══════════════════════════════════════════════════════════════════════════

    if area_sqm > 0 and area_sqm < 50:
        flags.append(RedFlag(
            "AREA_TOO_SMALL", "HIGH",
            f"📐 المساحة {area_sqm} م² صغيرة جداً — تأكد من الرقم",
            f"Area {area_sqm} m² seems wrong",
        ))
    elif area_sqm > 100_000:
        flags.append(RedFlag(
            "AREA_TOO_LARGE", "MEDIUM",
            f"📐 المساحة {area_sqm:,.0f} م² كبيرة جداً — تأكد من الرقم",
            f"Area {area_sqm:,.0f} m² seems wrong",
        ))
    elif area_sqm <= 0 and price_sar > 0:
        flags.append(RedFlag(
            "NO_AREA", "MEDIUM",
            "📐 المساحة غير مذكورة — لا يمكن حساب سعر المتر",
            "No area specified",
        ))

    # ═══════════════════════════════════════════════════════════════════════════
    # 7. ZONING MISMATCH (Balady GIS — only when lat/lon available)
    # ═══════════════════════════════════════════════════════════════════════════

    zoning = _balady_zoning_check(listing)
    if zoning and zoning.get("mismatch"):
        flags.append(RedFlag(
            "ZONING_MISMATCH", "HIGH",
            f"⛔ تعارض في الاستخدام: المعلن عنه [{zoning['advertised']}] لكن البلدي يسجله [{zoning['official']}] — تحقق قبل أي قرار",
            f"Listed: {zoning['advertised']} vs Balady official: {zoning['official']}",
        ))

    # ═══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    high_count = sum(1 for f in flags if f.severity == "HIGH")
    if high_count:
        logger.warning(
            f"Red flags for {listing.get('listing_id', '?')}: "
            f"{high_count} HIGH, {len(flags)} total"
        )

    return flags


def has_blocking_flags(flags: list[RedFlag]) -> bool:
    """Return True if any HIGH-severity red flag is present."""
    return any(f.severity == "HIGH" for f in flags)


def format_flags_arabic(flags: list[RedFlag]) -> str:
    """Format all flags as a single Arabic string for display/notification."""
    if not flags:
        return "✅ لا توجد علامات تحذيرية"
    lines = []
    for f in sorted(flags, key=lambda x: {"HIGH": 0, "MEDIUM": 1, "LOW": 2}[x.severity]):
        lines.append(f.message_ar)
    return "\n".join(lines)
