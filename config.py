import os
from dotenv import load_dotenv

load_dotenv()

# Local AI
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_MODEL_FAST = os.getenv("OLLAMA_MODEL_FAST", "qwen2.5:3b")
COMFYUI_API_URL = os.getenv("COMFYUI_API_URL", "http://localhost:8188")
SD_CHECKPOINT = os.getenv("SD_CHECKPOINT", "v1-5-pruned-emaonly.ckpt")

# WhatsApp Base Settings
BROKER_WHATSAPP = os.getenv("BROKER_WHATSAPP")
WA_BRIDGE_PORT = int(os.getenv("WA_BRIDGE_PORT", 3001))
PYTHON_BRIDGE_PORT = int(os.getenv("PYTHON_BRIDGE_PORT", 3002))
WA_MONITORED_GROUPS = [g.strip() for g in os.getenv("WA_MONITORED_GROUPS", "").split(",") if g.strip()]

# Scraper Settings
AQAR_DB_PATH = os.getenv("AQAR_DB_PATH")
WASALT_DB_PATH = os.getenv("WASALT_DB_PATH")

PRICE_MIN = int(os.getenv("PRICE_MIN_SAR", 500000))
PRICE_MAX = int(os.getenv("PRICE_MAX_SAR", 3750000))

TARGET_CITIES = [c.strip() for c in os.getenv("TARGET_CITIES", "جدة,الرياض,الدمام,مكة,المدينة,الطائف,أبها,تبوك,القصيم,حائل,جازان,نجران,الجوف,الخبر,القطيف").split(",")]

# AI Evaluation logic parameters
MIN_MATCH_SCORE = float(os.getenv("MIN_MATCH_SCORE", 0.65))
MIN_OPPORTUNITY_SCORE = float(os.getenv("MIN_OPPORTUNITY_SCORE", 6.0))

# Financial logic
CONSTRUCTION_COST = {
    "apartments": int(os.getenv("CONSTRUCTION_COST_APARTMENTS", 2200)),
    "villas": int(os.getenv("CONSTRUCTION_COST_VILLAS", 2800)),
    "commercial": 3000,
    "mixed": 2500,
}
SELL_PRICE = {
    "apartments": int(os.getenv("SELL_PRICE_APARTMENTS_SQM", 6500)),
    "villas": int(os.getenv("SELL_PRICE_VILLAS_SQM", 5800)),
    "commercial": 9000,
    "mixed": 7000,
}
FAR = {"apartments": 3.0, "villas": 1.0, "commercial": 2.5, "mixed": 2.0}
UNIT_SIZE_SQM = {"apartments": 120, "villas": 350, "commercial": 200, "mixed": 150}

# Feature toggles
FEATURES = {
    "whatsapp_monitor": os.getenv("FEATURE_WHATSAPP_MONITOR", "true") == "true",
    "platform_scraping": os.getenv("FEATURE_PLATFORM_SCRAPING", "true") == "true",
    "ai_mockup": os.getenv("FEATURE_AI_MOCKUP", "true") == "true",
    "pdf_proposal": os.getenv("FEATURE_PDF_PROPOSAL", "true") == "true",
    "auto_match": os.getenv("FEATURE_AUTO_MATCH", "true") == "true",
}

# Default runtime sources: web scraping for discovery + optional DB adapters.
ENABLED_SOURCES = ["aqar", "haraj", "bayut", "propertyfinder", "wasalt"]


def validate_config() -> None:
    """Warn about missing or inconsistent configuration at startup."""
    from core.logger import get_logger
    log = get_logger("config")

    warnings = []

    if not BROKER_WHATSAPP:
        warnings.append("BROKER_WHATSAPP غير مضبوط — لن تصل أي إشعارات للوسيط")

    if FEATURES["whatsapp_monitor"] and not WA_MONITORED_GROUPS:
        warnings.append("FEATURE_WHATSAPP_MONITOR=true لكن WA_MONITORED_GROUPS فارغ")

    if FEATURES["platform_scraping"] and "wasalt" in ENABLED_SOURCES and not WASALT_DB_PATH:
        warnings.append("wasalt source مفعّل لكن WASALT_DB_PATH غير مضبوط")

    if not (0 < MIN_MATCH_SCORE < 1):
        warnings.append(f"MIN_MATCH_SCORE={MIN_MATCH_SCORE} يجب أن يكون بين 0 و 1")

    for w in warnings:
        log.warning(w)

    enabled = [k for k, v in FEATURES.items() if v]
    disabled = [k for k, v in FEATURES.items() if not v]
    log.info(f"Features مُفعَّلة: {enabled}")
    if disabled:
        log.info(f"Features مُعطَّلة: {disabled}")
