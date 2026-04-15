"""
Classifies WhatsApp messages using Ollama.
"""
import json
import uuid
from datetime import datetime
from ollama import Client
from config import OLLAMA_API_URL, OLLAMA_MODEL_FAST
from core.logger import get_logger

logger = get_logger("classifier")


def _extract_json(text: str) -> str:
    """Extract the outermost JSON object from a string."""
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text

client = Client(host=OLLAMA_API_URL)

SYSTEM_PROMPT = """أنت محلل رسائل عقارية سعودية متخصص.

حلل الرسالة وأرجع JSON فقط بهذا الهيكل، بدون أي نص إضافي:
{
  "msg_type": "offer" أو "request" أو "irrelevant",
  "property_type": "أرض" أو "فيلا" أو "شقة" أو "عمارة" أو "دور" أو "تجاري" أو null,
  "city": "string or null",
  "district": "string or null",
  "area_sqm": number or null,
  "price_sar": number or null,
  "price_negotiable": boolean,
  "description": "ملخص الرسالة بجملة واحدة",
  "confidence": number (0-1)
}

تعريفات:
- offer: شخص يعرض عقار للبيع أو الإيجار
- request: شخص يبحث عن عقار ليشتريه أو يستأجره
- irrelevant: رسائل عامة، إعلانات غير عقارية، تحيات

أمثلة:
- "للبيع أرض في النرجس ٦٠٠ متر بـ ٢.٥ مليون" -> offer
- "مطلوب فيلا في حي الملقا لا تتجاوز ٣ مليون" -> request
- "ربنا يوفق الجميع" -> irrelevant"""


def classify_message(raw_msg: dict) -> dict:
    text = raw_msg.get("raw_text", "").strip()
    if not text or len(text) < 10:
        raw_msg["msg_type"] = "irrelevant"
        return raw_msg

    try:
        response = client.chat(
            model=OLLAMA_MODEL_FAST,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text}
            ],
            format="json",
            options={"temperature": 0.1, "num_gpu": 10}
        )
        raw = response.message.content.strip()
        parsed = json.loads(_extract_json(raw))

        raw_msg.update({
            "msg_type": parsed.get("msg_type", "irrelevant"),
            "property_type": parsed.get("property_type"),
            "city": parsed.get("city"),
            "district": parsed.get("district"),
            "area_sqm": parsed.get("area_sqm"),
            "price_sar": parsed.get("price_sar"),
            "price_negotiable": parsed.get("price_negotiable", False),
            "description": parsed.get("description"),
            "classification_confidence": parsed.get("confidence", 0),
            "message_id": raw_msg.get("message_id") or str(uuid.uuid4()),
        })

    except Exception as e:
        logger.error(f"Classification error: {e}")
        raw_msg["msg_type"] = "irrelevant"

    return raw_msg
