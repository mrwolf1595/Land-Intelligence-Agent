"""
Uses Ollama to analyze Land Opportunity text.
No vision model - pure text metrics.
"""
import json
from ollama import Client
from config import OLLAMA_API_URL, OLLAMA_MODEL


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

def analyze_land(listing_data: dict) -> dict:
    prompt = f"""
العنوان: {listing_data.get('title', '')}
المدينة/الحي: {listing_data.get('city', '')} / {listing_data.get('district', '')}
المساحة: {listing_data.get('area_sqm', 0)}
السعر المعروض: {listing_data.get('price_sar', 0)}
"""
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
        return parsed
    except Exception as e:
        print(f"[analyzer] Error: {e}")
        return {"opportunity_score": 0, "score_reasoning": str(e)}
