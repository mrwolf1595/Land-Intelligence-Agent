# ✅ خطة التنفيذ المعدّلة — Land Intelligence Agent v2
# 100% Free & Open Source — No Commercial APIs

---

## ✅ ما وافقت عليه من الخطة الأصلية (يتنفذ كما هو)

- Project structure — نفس الهيكل
- WhatsApp: whatsapp-web.js ✅
- Database: SQLite ✅
- Dashboard: Streamlit ✅
- PDF: WeasyPrint + Jinja2 ✅
- APScheduler للـ orchestration ✅

---

## ❌ تعديلات إلزامية قبل الكود

### تعديل 1 — Ollama API (مش HTTP raw)

الخطة قالت "Ollama HTTP API" — صح، بس استخدم الـ official Python library
مش تبني HTTP calls يدوي.

```python
# ❌ غلط
import httpx
httpx.post("http://localhost:11434/api/generate", ...)

# ✅ صح
from ollama import Client
client = Client(host="http://localhost:11434")
response = client.chat(
    model="qwen2.5:7b",
    messages=[{"role": "user", "content": prompt}],
    format="json",   # مهم جداً لمنع الـ malformed JSON
    options={"temperature": 0.1, "num_gpu": 20}
)
```

أضف للـ requirements.txt:
```
ollama>=0.2.0
```

---

### تعديل 2 — ComfyUI: استخدم workflow JSON مش custom scripts

ComfyUI عنده REST API جاهز — مش محتاج تبني integration من الصفر.
Pipeline الصح:

```python
# pipeline/mockup.py
import httpx, json, uuid, time

COMFYUI_URL = "http://localhost:8188"

# 1. ابعت workflow
def queue_prompt(workflow: dict) -> str:
    r = httpx.post(f"{COMFYUI_URL}/prompt", json={"prompt": workflow})
    return r.json()["prompt_id"]

# 2. استنى الـ output
def wait_for_image(prompt_id: str, timeout=120) -> bytes:
    start = time.time()
    while time.time() - start < timeout:
        history = httpx.get(f"{COMFYUI_URL}/history/{prompt_id}").json()
        if prompt_id in history:
            filename = history[prompt_id]["outputs"]["9"]["images"][0]["filename"]
            img = httpx.get(f"{COMFYUI_URL}/view?filename={filename}")
            return img.content
        time.sleep(2)
    raise TimeoutError("ComfyUI timeout")
```

Workflow JSON للـ SD1.5 txt2img على 4GB VRAM:
```json
{
  "4": {"class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.ckpt"}},
  "6": {"class_type": "CLIPTextEncode",
        "inputs": {"text": "POSITIVE_PROMPT", "clip": ["4", 1]}},
  "7": {"class_type": "CLIPTextEncode",
        "inputs": {"text": "ugly, blurry, low quality", "clip": ["4", 1]}},
  "3": {"class_type": "KSampler",
        "inputs": {"seed": 42, "steps": 20, "cfg": 7,
                   "sampler_name": "euler", "scheduler": "normal",
                   "denoise": 1.0, "model": ["4", 0],
                   "positive": ["6", 0], "negative": ["7", 0],
                   "latent_image": ["5", 0]}},
  "5": {"class_type": "EmptyLatentImage",
        "inputs": {"width": 512, "height": 512, "batch_size": 1}},
  "8": {"class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
  "9": {"class_type": "SaveImage",
        "inputs": {"filename_prefix": "land_mockup", "images": ["8", 0]}}
}
```

ComfyUI لازم يشتغل بـ:
```bash
python main.py --lowvram --listen 0.0.0.0
```

---

### تعديل 3 — Analyzer بدون Vision (Ollama نصي بس)

الـ RTX 3050 بـ 4GB مش هيشيل vision model + SD في نفس الوقت.
`pipeline/analyzer.py` يشتغل على النص فقط:

```python
ANALYZER_PROMPT = """أنت محلل عقاري سعودي خبير.
بناءً على نص الإعلان فقط، أرجع JSON فقط:
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
- بدون مشاكل قانونية مذكورة: +1 نقطة"""
```

---

## 📋 requirements.txt النهائي (معدّل)

```
ollama>=0.2.0
httpx>=0.27.0
python-dotenv>=1.0.0
streamlit>=1.35.0
pandas>=2.2.0
pillow>=10.0.0
pydantic>=2.0.0
apscheduler>=3.10.0
fastapi>=0.110.0
uvicorn>=0.29.0
weasyprint>=60.0
jinja2>=3.1.0
arabic-reshaper>=3.0.0
python-bidi>=0.4.2
```

---

## 📋 package.json (بدون تغيير)

```json
{
  "name": "land-agent-whatsapp",
  "version": "1.0.0",
  "main": "sources/whatsapp/client.js",
  "scripts": {
    "start": "node sources/whatsapp/client.js"
  },
  "dependencies": {
    "whatsapp-web.js": "^1.23.0",
    "qrcode-terminal": "^0.12.0",
    "express": "^4.18.0",
    "axios": "^1.6.0"
  }
}
```

---

## 🔐 .env.example النهائي

```env
# ── Local AI ──────────────────────────────
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_MODEL_FAST=qwen2.5:3b
COMFYUI_API_URL=http://localhost:8188
SD_CHECKPOINT=v1-5-pruned-emaonly.ckpt

# ── WhatsApp ───────────────────────────────
BROKER_WHATSAPP=+966XXXXXXXXX
WA_BRIDGE_PORT=3001
PYTHON_BRIDGE_PORT=3002
WA_MONITORED_GROUPS=جروب عقارات جدة,عقارات الرياض,فرص عقارية الدمام

# ── Geographic Coverage ────────────────────
TARGET_CITIES=جدة,الرياض,الدمام,مكة,المدينة,الطائف,أبها,تبوك,القصيم,حائل,جازان,نجران,الجوف,الخبر,القطيف

# ── Price Filters ──────────────────────────
PRICE_MIN_SAR=500000
PRICE_MAX_SAR=3750000

# ── Thresholds ─────────────────────────────
MIN_MATCH_SCORE=0.65
MIN_OPPORTUNITY_SCORE=6.0

# ── Financial Benchmarks (SAR/sqm) ─────────
CONSTRUCTION_COST_APARTMENTS=2200
CONSTRUCTION_COST_VILLAS=2800
SELL_PRICE_APARTMENTS_SQM=6500
SELL_PRICE_VILLAS_SQM=5800

# ── Existing Scrapers DB Paths ─────────────
AQAR_DB_PATH=/mnt/Kali desktop/Scraper_data/aqar.db
WASALT_DB_PATH=/mnt/Kali desktop/Scraper_data/wasalt.db

# ── Feature Flags ──────────────────────────
FEATURE_WHATSAPP_MONITOR=true
FEATURE_PLATFORM_SCRAPING=true
FEATURE_AI_MOCKUP=true
FEATURE_PDF_PROPOSAL=true
FEATURE_AUTO_MATCH=true
```

---

## ❓ إجابات على أسئلة الـ AI

**سؤال 1 — Existing Scraper Structure:**
اقرأ من الـ SQLite الأصلية مباشرةً (read-only) ومتنسخش البيانات.
استخدم `ATTACH DATABASE` أو `sqlite3.connect(AQAR_DB_PATH)` مباشرة.
متضافش في `agent.db` إلا اللي اتحلل فعلاً.

**سؤال 2 — Analyzer بدون Vision:**
نعم — نصي بالكامل. opportunity_score يتحسب من:
السعر vs متوسط الحي + المساحة + الوصف.
مفيش image analysis خالص في المرحلة دي.

**سؤال 3 — ComfyUI Workflow:**
استخدم الـ vanilla SD1.5 workflow اللي في التعديل 2 فوق.
لو مفيش checkpoint موجود: `wget https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned-emaonly.ckpt -P models/checkpoints/`

---

## ⚠️ Risk Flags المعدّلة

| الخطر | الحل |
|-------|------|
| VRAM 4GB: Ollama + ComfyUI في نفس الوقت | ComfyUI `--lowvram` + Ollama بـ `num_gpu: 10` (يوزع على CPU+GPU) |
| Ollama JSON malformed | `format="json"` في كل call + try/except + regex fallback `\{.*\}` |
| Arabic في WeasyPrint | arabic-reshaper + python-bidi قبل كل render + Amiri font |
| WhatsApp session انقطع | auto-reconnect loop في client.js + إشعار واتساب لك |
| الـ scraper DB path فيها مسافة | استخدم `Path()` من pathlib مش string concatenation |

---

## ✅ موافق على البدء؟

لو الخطة تمام، قول **proceed** وهيبدأ Phase 0 فوراً:
- إنشاء كل المجلدات والملفات الفارغة
- `core/database.py` + `core/models.py`
- `config.py` + `.env.example`
- `requirements.txt` + `package.json`
