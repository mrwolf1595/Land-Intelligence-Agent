"""
Uses Ollama to analyze Land Opportunity text.
No vision model - pure text metrics.

Includes:
  - Market-context injection from price benchmarks
  - Rule-based fallback scoring when Ollama is unavailable
  - Confidence tagging (HIGH / MEDIUM / LOW)
"""
import json
from ollama import Client
from config import OLLAMA_API_URL, OLLAMA_MODEL
from core.logger import get_logger
from pipeline.benchmarks import get_benchmark

logger = get_logger("analyzer")


def _extract_json(text: str) -> str:
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text

client = Client(host=OLLAMA_API_URL)

ANALYZER_PROMPT = """أنت محلل عقاري سعودي خبير.
بناءً على معلومات الإعلان فقط، أرجع JSON فقط:
{
  "land_area_sqm": number or null,
  "location": "string",
  "asking_price_sar": number,
  "price_per_sqm": number or null,
  "recommended_development": "apartments"|"villas"|"commercial"|"mixed",
  "development_reasoning": "string بالعربي",
  "estimated_units": number,
  "opportunity_score": number (0-10),
  "score_reasoning": "string بالعربي",
  "flags": ["string"],
  "risks": ["string"],
  "market_notes": "string"
}

معايير opportunity_score:
- سعر المتر أقل من متوسط الحي: +2 نقطة
- مساحة مناسبة للتطوير (>400م²): +2 نقطة
- موقع متميز أو قريب من خدمات: +2 نقطة
- سعر تفاوضي: +1 نقطة
- بدون مشاكل قانونية مذكورة: +1 نقطة
"""


def _rule_based_score(listing_data: dict) -> float:
    """Market-relative rule-based score using price benchmarks."""
    score = 0.0
    price_sar = float(listing_data.get("price_sar") or 0)
    area_sqm  = float(listing_data.get("area_sqm") or 0)
    city      = listing_data.get("city", "")
    district  = listing_data.get("district", "")
    price_sqm = price_sar / area_sqm if area_sqm > 0 else 0

    bench = get_benchmark(city, district) or get_benchmark(city, "")
    if bench and bench["count"] >= 3 and price_sqm > 0:
        ratio = price_sqm / bench["avg"]
        if ratio < 0.75:    score += 4.0   # >25% below market
        elif ratio < 0.90:  score += 3.0   # 10-25% below
        elif ratio < 1.00:  score += 1.5   # slightly below
        elif ratio < 1.10:  score += 0.5   # at market
        else:               score -= 1.0   # overpriced
    else:
        # No benchmark available — use simple area heuristic
        if area_sqm >= 600:    score += 2.5
        elif area_sqm >= 300:  score += 1.5

    if listing_data.get("contact_phone"):
        score += 1.0

    PREMIUM = {"الرياض", "جدة", "مكة المكرمة", "المدينة المنورة", "مكة", "المدينة"}
    if city in PREMIUM:
        score += 1.0

    if 100_000 <= price_sar <= 50_000_000:
        score += 1.0

    return min(max(score, 0.0), 10.0)


def _build_market_context(city: str, district: str, price_sqm: float) -> str:
    """Build Arabic market context string for Ollama prompt injection."""
    bench = get_benchmark(city, district) or get_benchmark(city, "")
    if not bench or price_sqm <= 0:
        return ""
    ratio = price_sqm / bench["avg"]
    pct = abs(1 - ratio) * 100
    direction = "أرخص" if ratio < 1 else "أغلى"
    return f"""
=== سياق السوق ===
متوسط سعر م² في {city}{' - ' + district if district else ''}: {bench['avg']:,.0f} ريال
هذا العقار {direction} من متوسط السوق بنسبة {pct:.1f}%
حجم العينة: {bench['count']} عقار
==================
"""


def _determine_confidence(bench: dict | None, ollama_ok: bool) -> str:
    """Determine analysis confidence level."""
    if bench and bench["count"] >= 10 and ollama_ok:
        return "HIGH"
    elif (bench and bench["count"] >= 3) or ollama_ok:
        return "MEDIUM"
    return "LOW"


def analyze_land(listing_data: dict) -> dict:
    city = listing_data.get("city", "")
    district = listing_data.get("district", "")
    area_sqm = float(listing_data.get("area_sqm") or 0)
    price_sar = float(listing_data.get("price_sar") or 0)
    price_sqm = price_sar / area_sqm if area_sqm > 0 else 0

    # Get benchmark for confidence determination
    bench = get_benchmark(city, district) or get_benchmark(city, "")

    # Build market context for prompt
    market_ctx = _build_market_context(city, district, price_sqm)

    prompt = f"""{market_ctx}
العنوان: {listing_data.get('title', '')}
المدينة/الحي: {city} / {district}
المساحة: {area_sqm}
السعر المعروض: {price_sar}
"""
    ollama_ok = False
    try:
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": ANALYZER_PROMPT},
                {"role": "user", "content": prompt}
            ],
            format="json",
            options={"temperature": 0.1, "num_gpu": 10}
        )
        raw = response.message.content.strip()
        parsed = json.loads(_extract_json(raw))
        parsed["source_url"] = listing_data.get("source_url", "")
        ollama_ok = True

        # Determine confidence
        parsed["confidence"] = _determine_confidence(bench, ollama_ok)

        # Inject benchmark info if available
        if bench:
            parsed["benchmark_avg_sqm"] = bench["avg"]
            parsed["benchmark_sample_count"] = bench["count"]

        return parsed
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        # Fall back to rule-based scoring
        fallback_score = _rule_based_score(listing_data)
        confidence = _determine_confidence(bench, ollama_ok=False)
        result = {
            "opportunity_score": fallback_score,
            "score_reasoning": f"تقييم تلقائي (rule-based): {e}",
            "asking_price_sar": price_sar,
            "land_area_sqm": area_sqm,
            "price_per_sqm": price_sqm if price_sqm > 0 else None,
            "location": f"{city} / {district}",
            "recommended_development": "apartments",
            "confidence": confidence,
            "source_url": listing_data.get("source_url", ""),
        }
        if bench:
            result["benchmark_avg_sqm"] = bench["avg"]
            result["benchmark_sample_count"] = bench["count"]
        return result
