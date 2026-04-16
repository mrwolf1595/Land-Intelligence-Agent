"""
Matches requests with offers using Ollama.
Returns match score + Arabic reasoning for broker review.
"""
import json
import uuid
from ollama import Client
from config import OLLAMA_API_URL, OLLAMA_MODEL, MIN_MATCH_SCORE
from core.database import get_unmatched, save_match
from core.logger import get_logger

logger = get_logger("matcher")


def _extract_json(text: str) -> str:
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text

client = Client(host=OLLAMA_API_URL)

MATCH_SYSTEM = """أنت وسيط عقاري خبير.
قيّم مدى تطابق طلب مع عرض عقاري وأرجع JSON فقط:
{
  "match_score": number (0.0-1.0),
  "reasoning": "string (سبب التطابق أو عدمه بالعربي في جملتين)",
  "key_gaps": ["string (نقاط اختلاف مهمة)"],
  "broker_tip": "string (نصيحة للوسيط كيف يقدم هذا المتطابق)"
}

معايير التطابق:
- المدينة والحي (وزن ٣٠٪)
- نوع العقار (وزن ٢٥٪)
- السعر (±٢٠٪ مقبول) (وزن ٢٥٪)
- المساحة (±٣٠٪ مقبول) (وزن ٢٠٪)"""


def run_matching() -> list[dict]:
    # Keep limits low so each cycle finishes well within the 10-minute window.
    # With Ollama taking ~1-3s per call: 10 req × 20 offers = max 200 calls ≈ 3-10 min.
    requests = get_unmatched("request", limit=10)
    offers   = get_unmatched("offer",   limit=20)

    if not requests or not offers:
        return []

    new_matches = []
    import time as _time
    _cycle_start = _time.time()
    _MAX_CYCLE_SEC = 480  # hard stop at 8 min to leave room for next cycle

    for req in requests:
        if _time.time() - _cycle_start > _MAX_CYCLE_SEC:
            logger.warning("Matching cycle hit time budget — stopping early")
            break
        best_score = 0
        best_match = None

        for offer in offers:
            if req.get("city") and offer.get("city"):
                if req["city"] not in offer["city"] and offer["city"] not in req["city"]:
                    continue

            score_data = _score_match(req, offer)
            if score_data["match_score"] > best_score:
                best_score = score_data["match_score"]
                best_match = (offer, score_data)

        if best_match and best_score >= MIN_MATCH_SCORE:
            offer, score_data = best_match
            match = {
                "match_id": str(uuid.uuid4()),
                "request_id": req["id"],
                "offer_id": offer["id"],
                "match_score": score_data["match_score"],
                "match_reasoning": score_data["reasoning"],
                "broker_tip": score_data.get("broker_tip", ""),
                "key_gaps": json.dumps(score_data.get("key_gaps", []), ensure_ascii=False),
            }
            save_match(match)
            new_matches.append({**match, **{
                "req_text": req["raw_text"], "req_name": req["sender_name"],
                "req_city": req["city"], "req_price": req["price_sar"],
                "off_text": offer["raw_text"], "off_name": offer["sender_name"],
                "off_city": offer["city"], "off_price": offer["price_sar"],
            }})

    return new_matches


def _score_match(req: dict, offer: dict) -> dict:
    prompt = f"""الطلب:
{req.get('raw_text', '')}
المدينة: {req.get('city')} | النوع: {req.get('property_type')} | السعر: {req.get('price_sar')} | المساحة: {req.get('area_sqm')}

العرض:
{offer.get('raw_text', '')}
المدينة: {offer.get('city')} | النوع: {offer.get('property_type')} | السعر: {offer.get('price_sar')} | المساحة: {offer.get('area_sqm')}"""

    try:
        response = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": MATCH_SYSTEM},
                {"role": "user", "content": prompt}
            ],
            format="json",
            options={"temperature": 0.1, "num_gpu": 10}
        )
        raw = response.message.content.strip()
        return json.loads(_extract_json(raw))
    except Exception as e:
        logger.error(f"Scoring error: {e}")
        return {"match_score": 0, "reasoning": "خطأ في التقييم", "broker_tip": "", "key_gaps": []}
