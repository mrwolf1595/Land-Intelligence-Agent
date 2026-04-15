# 🏗️ Land Intelligence Agent v2 — Full Claude Code Prompt
# Saudi Real Estate Matching Agent + WhatsApp Integration

---

## 📌 PROJECT OVERVIEW

A modular, extensible AI agent that:
1. Monitors Saudi real estate WhatsApp groups (via WhatsApp Web JS — free, no subscription)
2. Parses every message to classify it as **REQUEST** (طلب) or **OFFER** (عرض)
3. Runs intelligent matching between requests and offers
4. **Notifies YOU** (the broker) on WhatsApp with matched pairs + full context
5. You decide to act — contacting both parties directly as a licensed broker
6. Also scrapes listing platforms for additional inventory
7. Generates AI analysis + financial model + PDF proposal for high-value opportunities

### 🔑 Core Business Logic (Ethical & Legal)
```
WhatsApp Groups → Parse Messages → Classify → Match
                                                ↓
                              Notify BROKER (you) with match details
                                                ↓
                              Broker contacts both parties as intermediary
                              (both parties know broker is facilitating)
```

**No automated sending to group members without your review.**
**No hiding contact info from parties — you are the transparent intermediary.**
**Compliant with Saudi PDPL (Personal Data Protection Law).**

---

## 🗂️ EXTENSIBLE PROJECT STRUCTURE

```
land-agent/
├── main.py                        # Orchestrator
├── config.py                      # Central config + feature flags
├── .env                           # API keys
│
├── core/
│   ├── database.py                # SQLite — all persistent state
│   ├── models.py                  # Pydantic models (Listing, Request, Match, etc.)
│   ├── logger.py                  # Structured logging
│   └── scheduler.py               # APScheduler — periodic tasks
│
├── sources/                       # 🔌 PLUGGABLE DATA SOURCES
│   ├── base.py                    # Abstract base class for all sources
│   ├── whatsapp/
│   │   ├── client.js              # WhatsApp Web JS bot (Node.js)
│   │   ├── parser.py              # Message classifier (Claude API)
│   │   └── bridge.py             # Python ↔ Node.js bridge (HTTP)
│   ├── aqar/
│   │   └── scraper.py             # Aqar.fm scraper (existing)
│   ├── wasalt/
│   │   └── scraper.py             # Wasalt scraper (existing)
│   └── [new_source]/              # Add new source here (Bayut, Haraj, etc.)
│       └── scraper.py
│
├── pipeline/
│   ├── classifier.py              # Classify message: offer/request/irrelevant
│   ├── matcher.py                 # Match requests ↔ offers (Claude API)
│   ├── analyzer.py                # Land analysis — Claude Vision (Module A)
│   ├── mockup.py                  # Image generation — Replicate (Module B)
│   ├── financial.py               # ROI financial model (Module C)
│   ├── proposal.py                # PDF proposal generator (Module D)
│   └── notifier.py                # Notify broker via WhatsApp (Module E)
│
├── dashboard/
│   └── app.py                     # Streamlit review UI
│
├── output/
│   ├── reports/                   # Generated PDFs
│   └── mockups/                   # Before/after images
│
├── db/
│   └── agent.db                   # SQLite database
│
├── logs/
│   └── agent.log
│
├── requirements.txt               # Python deps
├── package.json                   # Node.js deps (WhatsApp)
└── README.md
```

---

## ⚙️ EXTENSIBILITY DESIGN PRINCIPLES

### Adding a new data source (e.g., Bayut, Haraj, Telegram):
1. Create `sources/bayut/scraper.py`
2. Inherit from `sources/base.py → BaseSource`
3. Register in `config.py → ENABLED_SOURCES`
4. Done — orchestrator picks it up automatically

### Adding a new feature (e.g., rental matching, commercial leads):
1. Add feature flag in `config.py → FEATURES`
2. Add new pipeline module in `pipeline/`
3. Hook into `main.py → run_pipeline()`

### Adding a new notification channel (e.g., Telegram, Email):
1. Create `pipeline/notifiers/telegram.py`
2. Inherit from `pipeline/notifiers/base.py`
3. Register in config

---

## 🔐 .env

```env
# Anthropic
ANTHROPIC_API_KEY=your_key_here

# Replicate (image generation)
REPLICATE_API_TOKEN=your_token_here

# Your WhatsApp number (broker)
BROKER_WHATSAPP=+966XXXXXXXXX

# WhatsApp bridge (local Node.js server)
WA_BRIDGE_URL=http://localhost:3001

# Groups to monitor (comma-separated, exact names from WhatsApp)
WA_MONITORED_GROUPS=جروب عقارات جدة,عقارات الرياض,فرص عقارية الدمام

# Platform filters
PRICE_MIN_SAR=500000
PRICE_MAX_SAR=3750000
TARGET_CITIES=جدة,الرياض,الدمام,مكة,المدينة,الطائف,أبها,تبوك,القصيم,حائل,جازان,نجران,الجوف

# Feature flags
FEATURE_WHATSAPP_MONITOR=true
FEATURE_PLATFORM_SCRAPING=true
FEATURE_AI_MOCKUP=true
FEATURE_PDF_PROPOSAL=true
FEATURE_AUTO_MATCH=true

# Matching thresholds
MIN_MATCH_SCORE=0.65
MIN_OPPORTUNITY_SCORE=6.0

# Construction cost benchmarks (SAR/sqm)
CONSTRUCTION_COST_APARTMENTS=2200
CONSTRUCTION_COST_VILLAS=2800
SELL_PRICE_APARTMENTS_SQM=6500
SELL_PRICE_VILLAS_SQM=5800
```

---

## 📋 requirements.txt

```
anthropic>=0.25.0
replicate>=0.25.0
weasyprint>=60.0
jinja2>=3.1.0
httpx>=0.27.0
python-dotenv>=1.0.0
streamlit>=1.35.0
pandas>=2.2.0
pillow>=10.0.0
pydantic>=2.0.0
apscheduler>=3.10.0
fastapi>=0.110.0
uvicorn>=0.29.0
arabic-reshaper>=3.0.0
python-bidi>=0.4.2
```

---

## 📦 package.json (Node.js — WhatsApp)

```json
{
  "name": "land-agent-whatsapp",
  "version": "1.0.0",
  "description": "WhatsApp Web bridge for Land Agent",
  "main": "sources/whatsapp/client.js",
  "scripts": {
    "start": "node sources/whatsapp/client.js",
    "dev": "nodemon sources/whatsapp/client.js"
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

## 🔧 config.py

```python
import os
from dotenv import load_dotenv
load_dotenv()

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

# Broker info
BROKER_WHATSAPP = os.getenv("BROKER_WHATSAPP")
WA_BRIDGE_URL = os.getenv("WA_BRIDGE_URL", "http://localhost:3001")

# Monitored groups
WA_MONITORED_GROUPS = [
    g.strip() for g in os.getenv("WA_MONITORED_GROUPS", "").split(",") if g.strip()
]

# Geographic coverage — all Saudi regions
TARGET_CITIES = [
    g.strip() for g in os.getenv(
        "TARGET_CITIES",
        "جدة,الرياض,الدمام,مكة,المدينة,الطائف,أبها,تبوك,القصيم,حائل,جازان,نجران,الجوف,الخبر,القطيف"
    ).split(",")
]

# Price filters
PRICE_MIN = int(os.getenv("PRICE_MIN_SAR", 500000))
PRICE_MAX = int(os.getenv("PRICE_MAX_SAR", 3750000))

# Feature flags — toggle modules on/off
FEATURES = {
    "whatsapp_monitor": os.getenv("FEATURE_WHATSAPP_MONITOR", "true") == "true",
    "platform_scraping": os.getenv("FEATURE_PLATFORM_SCRAPING", "true") == "true",
    "ai_mockup": os.getenv("FEATURE_AI_MOCKUP", "true") == "true",
    "pdf_proposal": os.getenv("FEATURE_PDF_PROPOSAL", "true") == "true",
    "auto_match": os.getenv("FEATURE_AUTO_MATCH", "true") == "true",
}

# Enabled sources — add new scrapers here
ENABLED_SOURCES = [
    "aqar",
    "wasalt",
    # "bayut",    # uncomment to enable
    # "haraj",
    # "telegram",
]

# Thresholds
MIN_MATCH_SCORE = float(os.getenv("MIN_MATCH_SCORE", 0.65))
MIN_OPPORTUNITY_SCORE = float(os.getenv("MIN_OPPORTUNITY_SCORE", 6.0))

# Financial benchmarks
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
```

---

## 🗃️ core/models.py

```python
from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

class ParsedMessage(BaseModel):
    """A classified WhatsApp message."""
    message_id: str
    group_name: str
    sender_phone: str          # Stored locally, never forwarded
    sender_name: str
    raw_text: str
    timestamp: datetime
    msg_type: Literal["offer", "request", "irrelevant"]

    # Extracted fields
    property_type: Optional[str] = None   # أرض، فيلا، شقة، عمارة
    city: Optional[str] = None
    district: Optional[str] = None
    area_sqm: Optional[float] = None
    price_sar: Optional[float] = None
    price_negotiable: bool = False
    description: Optional[str] = None

    # Source tracking (for broker use only — not forwarded)
    source: str = "whatsapp"
    source_group: Optional[str] = None


class Match(BaseModel):
    """A matched request-offer pair."""
    match_id: str
    request: ParsedMessage
    offer: ParsedMessage
    match_score: float          # 0.0 - 1.0
    match_reasoning: str        # Arabic explanation
    created_at: datetime = datetime.now()
    broker_notified: bool = False
    broker_action: Optional[str] = None   # "contacted", "rejected", "pending"


class LandOpportunity(BaseModel):
    """A high-value land from platform scraping."""
    listing_id: str
    source: str                 # "aqar", "wasalt", etc.
    title: str
    city: str
    district: Optional[str] = None
    area_sqm: Optional[float] = None
    price_sar: float
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    image_urls: Optional[str] = None
    source_url: str
    scraped_at: datetime = datetime.now()

    # After analysis
    analysis: Optional[dict] = None
    financial: Optional[dict] = None
    pdf_path: Optional[str] = None
    processed: bool = False
```

---

## 🗃️ core/database.py

```python
import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = "db/agent.db"
Path("db").mkdir(exist_ok=True)

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            group_name TEXT,
            sender_phone TEXT,      -- stored locally, never forwarded
            sender_name TEXT,
            raw_text TEXT,
            msg_type TEXT,          -- offer/request/irrelevant
            property_type TEXT,
            city TEXT,
            district TEXT,
            area_sqm REAL,
            price_sar REAL,
            description TEXT,
            source TEXT DEFAULT 'whatsapp',
            timestamp TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS matches (
            id TEXT PRIMARY KEY,
            request_id TEXT,
            offer_id TEXT,
            match_score REAL,
            match_reasoning TEXT,
            broker_notified INTEGER DEFAULT 0,
            broker_action TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(request_id) REFERENCES messages(id),
            FOREIGN KEY(offer_id) REFERENCES messages(id)
        );

        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            city TEXT,
            district TEXT,
            area_sqm REAL,
            price_sar REAL,
            contact_phone TEXT,
            image_urls TEXT,
            source_url TEXT,
            analysis TEXT,          -- JSON blob
            financial TEXT,         -- JSON blob
            pdf_path TEXT,
            processed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()

def save_message(msg: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO messages
        (id, group_name, sender_phone, sender_name, raw_text, msg_type,
         property_type, city, district, area_sqm, price_sar, description, source, timestamp)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        msg["message_id"], msg["group_name"], msg["sender_phone"],
        msg["sender_name"], msg["raw_text"], msg["msg_type"],
        msg.get("property_type"), msg.get("city"), msg.get("district"),
        msg.get("area_sqm"), msg.get("price_sar"), msg.get("description"),
        msg.get("source", "whatsapp"), msg["timestamp"]
    ))
    conn.commit()
    conn.close()

def save_match(match: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO matches
        (id, request_id, offer_id, match_score, match_reasoning)
        VALUES (?,?,?,?,?)
    """, (
        match["match_id"], match["request_id"], match["offer_id"],
        match["match_score"], match["match_reasoning"]
    ))
    conn.commit()
    conn.close()

def get_unmatched(msg_type: str, limit: int = 50) -> list[dict]:
    """Get messages not yet part of a match."""
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT * FROM messages
        WHERE msg_type = ?
        AND id NOT IN (
            SELECT {'request_id' if msg_type == 'request' else 'offer_id'} FROM matches
        )
        ORDER BY timestamp DESC LIMIT ?
    """, (msg_type, limit)).fetchall()
    cols = [d[0] for d in conn.execute("PRAGMA table_info(messages)").fetchall()]
    conn.close()
    return [dict(zip(cols, r)) for r in rows]

def get_pending_matches() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT m.*, 
               req.raw_text as req_text, req.sender_name as req_name,
               req.sender_phone as req_phone, req.city as req_city,
               req.price_sar as req_price, req.area_sqm as req_area,
               off.raw_text as off_text, off.sender_name as off_name,
               off.sender_phone as off_phone, off.city as off_city,
               off.price_sar as off_price, off.area_sqm as off_area
        FROM matches m
        JOIN messages req ON m.request_id = req.id
        JOIN messages off ON m.offer_id = off.id
        WHERE m.broker_notified = 0
        ORDER BY m.match_score DESC
    """).fetchall()
    cols = [d[0] for d in conn.execute("PRAGMA table_info(matches)").fetchall()]
    extra = ["req_text","req_name","req_phone","req_city","req_price","req_area",
             "off_text","off_name","off_phone","off_city","off_price","off_area"]
    conn.close()
    return [dict(zip(cols + extra, r)) for r in rows]

def mark_match_notified(match_id: str):
    conn = get_conn()
    conn.execute("UPDATE matches SET broker_notified=1 WHERE id=?", (match_id,))
    conn.commit()
    conn.close()
```

---

## 📱 sources/whatsapp/client.js — WhatsApp Web JS Bot

```javascript
/**
 * WhatsApp Web JS Bridge
 * - Connects to WhatsApp Web (free, no API subscription needed)
 * - Monitors specified groups
 * - Forwards new messages to Python pipeline via HTTP
 * 
 * Setup:
 *   npm install
 *   node sources/whatsapp/client.js
 *   Scan QR code with your phone once → session saved locally
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const express = require('express');
const axios = require('axios');
const fs = require('fs');

// Load config
require('dotenv').config();
const PYTHON_BRIDGE_URL = process.env.PYTHON_BRIDGE_URL || 'http://localhost:3002/message';
const MONITORED_GROUPS = (process.env.WA_MONITORED_GROUPS || '').split(',').map(g => g.trim());
const BROKER_NUMBER = process.env.BROKER_WHATSAPP || '';

// Express server for Python → WhatsApp sending
const app = express();
app.use(express.json());

let waClient = null;

// ── WhatsApp Client Setup ──────────────────────────────────────────────
const client = new Client({
    authStrategy: new LocalAuth({ dataPath: '.wwebjs_auth' }),
    puppeteer: {
        headless: true,
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    }
});

client.on('qr', (qr) => {
    console.log('\n📱 Scan this QR code with your WhatsApp:');
    qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
    console.log('✅ WhatsApp connected successfully');
    waClient = client;
});

client.on('auth_failure', () => {
    console.error('❌ WhatsApp auth failed — delete .wwebjs_auth and retry');
});

// ── Message Listener ──────────────────────────────────────────────────
client.on('message', async (msg) => {
    try {
        // Only process group messages
        if (!msg.from.endsWith('@g.us')) return;

        const chat = await msg.getChat();
        const groupName = chat.name;

        // Only monitored groups
        if (!MONITORED_GROUPS.some(g => groupName.includes(g))) return;

        // Skip bot's own messages
        if (msg.fromMe) return;

        const contact = await msg.getContact();
        const senderPhone = contact.number || 'unknown';
        const senderName = contact.pushname || contact.name || senderPhone;

        const payload = {
            message_id: msg.id._serialized,
            group_name: groupName,
            sender_phone: senderPhone,    // stored in your local DB only
            sender_name: senderName,
            raw_text: msg.body,
            timestamp: new Date(msg.timestamp * 1000).toISOString(),
            has_media: msg.hasMedia,
        };

        console.log(`[${groupName}] ${senderName}: ${msg.body.slice(0, 80)}...`);

        // Forward to Python
        await axios.post(PYTHON_BRIDGE_URL, payload, { timeout: 5000 });

    } catch (e) {
        console.error('Message processing error:', e.message);
    }
});

// ── HTTP API: Python → Send WhatsApp to Broker ──────────────────────
app.post('/send', async (req, res) => {
    const { to, message } = req.body;
    if (!waClient) return res.status(503).json({ error: 'WhatsApp not ready' });
    
    try {
        // Format phone number for WhatsApp
        const chatId = to.replace(/\D/g, '') + '@c.us';
        await waClient.sendMessage(chatId, message);
        res.json({ success: true });
    } catch (e) {
        res.status(500).json({ error: e.message });
    }
});

app.get('/status', (req, res) => {
    res.json({ connected: !!waClient, groups: MONITORED_GROUPS });
});

app.listen(3001, () => console.log('🌉 WhatsApp bridge running on port 3001'));

client.initialize();
```

---

## 🧠 pipeline/classifier.py — Message Classifier

```python
"""
Classifies WhatsApp messages as: offer / request / irrelevant
Extracts structured fields using Claude API.
"""
import json
import uuid
from datetime import datetime
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY

client = Anthropic(api_key=ANTHROPIC_API_KEY)

SYSTEM_PROMPT = """أنت محلل رسائل عقارية سعودية متخصص.

حلل الرسالة وأرجع JSON فقط بهذا الهيكل، بدون أي نص إضافي:
{
  "msg_type": "offer"|"request"|"irrelevant",
  "property_type": "أرض"|"فيلا"|"شقة"|"عمارة"|"دور"|"تجاري"|null,
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
- "للبيع أرض في النرجس ٦٠٠ متر بـ ٢.٥ مليون" → offer
- "مطلوب فيلا في حي الملقا لا تتجاوز ٣ مليون" → request
- "ربنا يوفق الجميع" → irrelevant"""


def classify_message(raw_msg: dict) -> dict:
    """
    Input: raw message dict from WhatsApp bridge
    Output: enriched dict with classification + extracted fields
    """
    text = raw_msg.get("raw_text", "").strip()
    if not text or len(text) < 10:
        raw_msg["msg_type"] = "irrelevant"
        return raw_msg

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Fast + cheap for classification
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}]
        )
        raw = response.content[0].text.strip()
        clean = raw.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)

        # Merge into message dict
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
        print(f"[classifier] Error: {e}")
        raw_msg["msg_type"] = "irrelevant"

    return raw_msg
```

---

## 🔗 pipeline/matcher.py — Request ↔ Offer Matching

```python
"""
Matches requests with offers using Claude API.
Returns match score + Arabic reasoning for broker review.
"""
import json
import uuid
from anthropic import Anthropic
from config import ANTHROPIC_API_KEY, MIN_MATCH_SCORE
from core.database import get_unmatched, save_match

client = Anthropic(api_key=ANTHROPIC_API_KEY)

MATCH_SYSTEM = """أنت وسيط عقاري خبير.
قيّم مدى تطابق طلب مع عرض عقاري وأرجع JSON فقط:
{
  "match_score": number (0.0-1.0),
  "reasoning": "string — سبب التطابق أو عدمه بالعربي في جملتين",
  "key_gaps": ["string — نقاط اختلاف مهمة"],
  "broker_tip": "string — نصيحة للوسيط كيف يقدم هذا المتطابق"
}

معايير التطابق:
- المدينة والحي (وزن ٣٠٪)
- نوع العقار (وزن ٢٥٪)
- السعر (±٢٠٪ مقبول) (وزن ٢٥٪)
- المساحة (±٣٠٪ مقبول) (وزن ٢٠٪)"""


def run_matching() -> list[dict]:
    """
    Get unmatched requests and offers, run matching, save results.
    Returns list of new matches above threshold.
    """
    requests = get_unmatched("request", limit=30)
    offers = get_unmatched("offer", limit=50)

    if not requests or not offers:
        return []

    new_matches = []

    for req in requests:
        best_score = 0
        best_match = None

        for offer in offers:
            # Quick pre-filter: same city if both specified
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
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=MATCH_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip().replace("```json", "").replace("```", "")
        return json.loads(raw)
    except Exception as e:
        print(f"[matcher] Scoring error: {e}")
        return {"match_score": 0, "reasoning": "خطأ في التقييم", "broker_tip": "", "key_gaps": []}
```

---

## 📲 pipeline/notifier.py — Broker WhatsApp Notification

```python
"""
Sends match notifications to the BROKER (you) via WhatsApp.
Message format designed for quick broker decision-making.
NEVER sends to request/offer parties directly.
"""
import httpx
from config import WA_BRIDGE_URL, BROKER_WHATSAPP


def format_match_message(match: dict) -> str:
    """
    Format a clear, actionable match notification for the broker.
    Contact info of both parties included for broker use only.
    """
    score_pct = int(match["match_score"] * 100)
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
    """Send match notification to broker via WhatsApp bridge."""
    message = format_match_message(match)
    return _send_whatsapp(BROKER_WHATSAPP, message)


def notify_broker_opportunity(analysis: dict, financial: dict, pdf_path: str = None) -> bool:
    """Notify broker of a high-value land opportunity from platform scraping."""
    roi = financial.get("roi_pct", 0)
    score = analysis.get("opportunity_score", 0)

    msg = f"""🏗️ *فرصة عقارية عالية القيمة*
━━━━━━━━━━━━━━━━━━━━

📍 الموقع: {analysis.get('location', 'غير محدد')}
📐 المساحة: {analysis.get('land_area_sqm', '?')} م²
💰 السعر: {_fmt_price(analysis.get('asking_price_sar'))}
🏆 درجة الفرصة: {score}/10
🏢 التطوير المقترح: {_dev_label(analysis.get('recommended_development'))}

💹 *النموذج المالي:*
• إجمالي الاستثمار: {_fmt_price(financial.get('total_investment_sar'))}
• الإيرادات المتوقعة: {_fmt_price(financial.get('total_revenue_sar'))}
• صافي الربح: {_fmt_price(financial.get('gross_profit_sar'))}
• العائد: {roi}% خلال {financial.get('timeline_months', '?')} شهر

🔗 {analysis.get('source_url', '')}
{"📎 تم إرفاق الـ Proposal PDF" if pdf_path else ""}"""

    return _send_whatsapp(BROKER_WHATSAPP, msg)


def _send_whatsapp(to: str, message: str) -> bool:
    try:
        r = httpx.post(
            f"{WA_BRIDGE_URL}/send",
            json={"to": to, "message": message},
            timeout=10
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[notifier] WhatsApp send error: {e}")
        return False


def _fmt_price(price) -> str:
    if not price:
        return "غير محدد"
    return f"{int(price):,} ر.س"


def _dev_label(dev_type: str) -> str:
    return {
        "apartments": "عمارة شقق",
        "villas": "فلل مستقلة",
        "commercial": "تجاري",
        "mixed": "متعدد الاستخدامات"
    }.get(dev_type or "", "غير محدد")
```

---

## 🌐 sources/base.py — Abstract Base for All Sources

```python
"""
Base class for all data sources.
Any new source (Bayut, Haraj, Telegram, etc.) must inherit this.
"""
from abc import ABC, abstractmethod

class BaseSource(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self) -> list[dict]:
        """
        Fetch new listings/messages.
        Returns list of raw dicts with at minimum:
        {id, title, price_sar, city, source_url}
        """
        pass

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        """
        Normalize source-specific fields to unified schema.
        Must return dict compatible with LandOpportunity model.
        """
        pass

    def run(self) -> list[dict]:
        """Fetch + normalize."""
        raw_items = self.fetch()
        return [self.normalize(r) for r in raw_items if r]
```

---

## 🔌 sources/whatsapp/bridge.py — Python HTTP Receiver

```python
"""
Python side of the WhatsApp bridge.
Receives messages from Node.js client, pushes to classifier pipeline.
"""
from fastapi import FastAPI, BackgroundTasks
from core.database import save_message
from pipeline.classifier import classify_message

app = FastAPI()

@app.post("/message")
async def receive_message(payload: dict, background_tasks: BackgroundTasks):
    """Receive message from Node.js WhatsApp client."""
    background_tasks.add_task(process_message, payload)
    return {"status": "queued"}

async def process_message(raw_msg: dict):
    classified = classify_message(raw_msg)
    if classified["msg_type"] != "irrelevant":
        save_message(classified)
        print(f"[bridge] Saved {classified['msg_type']}: {classified.get('description', '')[:60]}")

# Run: uvicorn sources.whatsapp.bridge:app --port 3002
```

---

## 🚀 main.py — Orchestrator

```python
"""
Main orchestrator.

Run modes:
  python main.py --mode monitor    # WhatsApp monitoring loop
  python main.py --mode scrape     # Platform scraping
  python main.py --mode match      # Run matching on existing data
  python main.py --mode all        # Everything (use with scheduler)
"""
import argparse
import subprocess
import time
from apscheduler.schedulers.blocking import BlockingScheduler

from core.database import init_db
from pipeline.matcher import run_matching
from pipeline.notifier import notify_broker_match, notify_broker_opportunity
from pipeline.analyzer import analyze_land
from pipeline.mockup import generate_mockup
from pipeline.financial import calculate_roi
from pipeline.proposal import generate_proposal
from core.database import mark_match_notified, get_pending_matches
from config import FEATURES, ENABLED_SOURCES


def run_matching_cycle():
    """Match requests ↔ offers, notify broker."""
    if not FEATURES["auto_match"]:
        return
    print("[main] Running matching cycle...")
    matches = run_matching()
    print(f"[main] Found {len(matches)} new matches")
    for match in matches:
        if notify_broker_match(match):
            mark_match_notified(match["match_id"])


def run_scraping_cycle():
    """Scrape platforms, analyze high-value lands, notify broker."""
    if not FEATURES["platform_scraping"]:
        return

    for source_name in ENABLED_SOURCES:
        try:
            module = __import__(f"sources.{source_name}.scraper", fromlist=["Scraper"])
            scraper = module.Scraper()
            listings = scraper.run()
            print(f"[main] {source_name}: {len(listings)} listings")

            for listing in listings:
                _process_land_opportunity(listing)

        except Exception as e:
            print(f"[main] Source {source_name} error: {e}")


def _process_land_opportunity(listing: dict):
    """Full pipeline for a scraped land."""
    from core.database import is_processed, mark_processed
    lid = str(listing.get("id", ""))
    if not lid or is_processed("db/agent.db", lid):
        return

    try:
        analysis = analyze_land(listing)
        score = analysis.get("opportunity_score", 0)
        if score < float(__import__("config").MIN_OPPORTUNITY_SCORE):
            mark_processed("db/agent.db", lid, f"low_score_{score}")
            return

        financial = calculate_roi(analysis)
        mockup = generate_mockup(analysis) if FEATURES["ai_mockup"] else {}
        pdf = generate_proposal(analysis, financial, mockup) if FEATURES["pdf_proposal"] else None

        notify_broker_opportunity(analysis, financial, pdf)
        mark_processed("db/agent.db", lid, "done")

    except Exception as e:
        print(f"[main] Opportunity processing error: {e}")


def start_whatsapp_node():
    """Start Node.js WhatsApp client as subprocess."""
    print("[main] Starting WhatsApp Node.js client...")
    return subprocess.Popen(["node", "sources/whatsapp/client.js"])


def start_python_bridge():
    """Start FastAPI bridge as subprocess."""
    print("[main] Starting Python WhatsApp bridge...")
    return subprocess.Popen([
        "uvicorn", "sources.whatsapp.bridge:app",
        "--host", "0.0.0.0", "--port", "3002", "--log-level", "warning"
    ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["monitor", "scrape", "match", "all"], default="all")
    args = parser.parse_args()

    init_db()
    print(f"\n🏗️  Land Intelligence Agent v2 — Mode: {args.mode}\n")

    if args.mode in ("monitor", "all") and FEATURES["whatsapp_monitor"]:
        start_whatsapp_node()
        time.sleep(3)
        start_python_bridge()
        time.sleep(2)

    if args.mode == "match":
        run_matching_cycle()
        return

    if args.mode == "scrape":
        run_scraping_cycle()
        return

    # Mode: all — run scheduler
    scheduler = BlockingScheduler()
    scheduler.add_job(run_matching_cycle, "interval", minutes=2,   id="matching")
    scheduler.add_job(run_scraping_cycle, "interval", hours=1,     id="scraping")

    print("✅ Scheduler running. Press Ctrl+C to stop.\n")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n👋 Agent stopped.")


if __name__ == "__main__":
    main()
```

---

## 📊 dashboard/app.py — Streamlit Review UI

```python
"""
Broker dashboard — review matches and opportunities before acting.
Run: streamlit run dashboard/app.py
"""
import streamlit as st
import sqlite3
import json
import os

st.set_page_config(page_title="Land Agent Dashboard", layout="wide", page_icon="🏗️")
st.title("🏗️ Land Intelligence Agent — Broker Dashboard")

DB = "db/agent.db"

def get_conn(): return sqlite3.connect(DB)

tab1, tab2, tab3 = st.tabs(["🔗 تطابقات جديدة", "🏗️ فرص الأراضي", "📊 إحصائيات"])

# ── Tab 1: Matches ──────────────────────────────────────────────────────
with tab1:
    st.subheader("تطابقات الطلب والعرض — بانتظار قرارك")

    conn = get_conn()
    matches = conn.execute("""
        SELECT m.*, 
               req.raw_text, req.sender_name as req_name, req.sender_phone as req_phone,
               req.city as req_city, req.price_sar as req_price,
               off.raw_text as off_text, off.sender_name as off_name, off.sender_phone as off_phone,
               off.city as off_city, off.price_sar as off_price
        FROM matches m
        JOIN messages req ON m.request_id = req.id
        JOIN messages off ON m.offer_id = off.id
        WHERE m.broker_action = 'pending'
        ORDER BY m.match_score DESC
    """).fetchall()
    conn.close()

    if not matches:
        st.info("لا يوجد تطابقات جديدة حالياً")
    else:
        st.write(f"**{len(matches)} تطابق** بانتظار المراجعة")
        for m in matches:
            score = m[3]
            score_color = "🟢" if score >= 0.8 else "🟡" if score >= 0.65 else "🟠"
            with st.expander(f"{score_color} تطابق {int(score*100)}% — {m[13]} ↔ {m[17]}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**📋 الطالب**")
                    st.write(m[10])  # raw_text
                    st.caption(f"المدينة: {m[14]} | السعر: {m[15]:,.0f} ر.س" if m[15] else "")
                    # Show phone for broker only
                    st.code(f"رقم الاتصال: {m[12]}")
                with c2:
                    st.markdown("**🏗️ العارض**")
                    st.write(m[16])
                    st.caption(f"المدينة: {m[18]} | السعر: {m[19]:,.0f} ر.س" if m[19] else "")
                    st.code(f"رقم الاتصال: {m[20]}")

                st.info(f"💡 {m[4]}")  # match_reasoning

                col_a, col_b, col_c = st.columns(3)
                if col_a.button("✅ تواصلت", key=f"act_{m[0]}"):
                    conn2 = get_conn()
                    conn2.execute("UPDATE matches SET broker_action='contacted' WHERE id=?", (m[0],))
                    conn2.commit(); conn2.close(); st.rerun()
                if col_b.button("❌ تجاهل", key=f"rej_{m[0]}"):
                    conn2 = get_conn()
                    conn2.execute("UPDATE matches SET broker_action='rejected' WHERE id=?", (m[0],))
                    conn2.commit(); conn2.close(); st.rerun()

# ── Tab 2: Land Opportunities ───────────────────────────────────────────
with tab2:
    st.subheader("فرص الأراضي المحللة")
    conn = get_conn()
    opps = conn.execute("""
        SELECT * FROM opportunities WHERE processed=1 ORDER BY created_at DESC LIMIT 50
    """).fetchall()
    conn.close()

    if not opps:
        st.info("لا يوجد فرص محللة بعد")
    else:
        for o in opps:
            analysis = json.loads(o[10] or "{}") if o[10] else {}
            fin = json.loads(o[11] or "{}") if o[11] else {}
            score = analysis.get("opportunity_score", 0)
            roi = fin.get("roi_pct", 0)
            with st.expander(f"📍 {o[3]} — Score: {score}/10 | ROI: {roi}%"):
                c1, c2, c3 = st.columns(3)
                c1.metric("سعر الأرض", f"{o[6]:,.0f} ر.س" if o[6] else "—")
                c2.metric("صافي الربح", f"{fin.get('gross_profit_sar', 0):,.0f} ر.س")
                c3.metric("ROI", f"{roi}%")
                if o[12] and os.path.exists(o[12]):
                    with open(o[12], "rb") as f:
                        st.download_button("⬇️ تحميل Proposal PDF", f.read(),
                                           file_name=os.path.basename(o[12]),
                                           mime="application/pdf")

# ── Tab 3: Stats ────────────────────────────────────────────────────────
with tab3:
    conn = get_conn()
    stats = {
        "إجمالي الرسائل": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "طلبات": conn.execute("SELECT COUNT(*) FROM messages WHERE msg_type='request'").fetchone()[0],
        "عروض": conn.execute("SELECT COUNT(*) FROM messages WHERE msg_type='offer'").fetchone()[0],
        "تطابقات": conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0],
        "تم التواصل": conn.execute("SELECT COUNT(*) FROM matches WHERE broker_action='contacted'").fetchone()[0],
    }
    conn.close()
    cols = st.columns(len(stats))
    for col, (label, val) in zip(cols, stats.items()):
        col.metric(label, val)
```

---

## 📦 HOW TO RUN

```bash
# ── Python setup ──────────────────────────
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# ── Node.js setup (WhatsApp) ──────────────
npm install

# ── Configure ─────────────────────────────
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY, your phone number, group names

# ── First run: scan QR code ───────────────
node sources/whatsapp/client.js
# Scan QR with your phone → session saved → Ctrl+C

# ── Run full agent ────────────────────────
python main.py --mode all

# ── Dashboard (separate terminal) ─────────
streamlit run dashboard/app.py

# ── Scraping only ─────────────────────────
python main.py --mode scrape

# ── Matching only ─────────────────────────
python main.py --mode match
```

---

## ✅ CLAUDE CODE IMPLEMENTATION CHECKLIST

### Phase 0 — Setup
- [ ] Create full directory structure
- [ ] Install Python + Node.js dependencies
- [ ] Configure `.env` with real values
- [ ] Test WhatsApp QR scan and connection

### Phase 1 — WhatsApp Pipeline
- [ ] Implement `sources/whatsapp/client.js`
- [ ] Implement `sources/whatsapp/bridge.py`
- [ ] Implement `pipeline/classifier.py`
- [ ] Test: send test message to monitored group, verify classification

### Phase 2 — Matching Engine
- [ ] Implement `core/database.py` + `core/models.py`
- [ ] Implement `pipeline/matcher.py`
- [ ] Implement `pipeline/notifier.py`
- [ ] Test: inject mock request + offer, verify match notification sent to broker

### Phase 3 — Land Opportunity Pipeline
- [ ] Implement `sources/base.py`
- [ ] Connect existing Aqar/Wasalt scrapers as sources
- [ ] Implement `pipeline/analyzer.py` (Claude Vision)
- [ ] Implement `pipeline/financial.py`
- [ ] Implement `pipeline/mockup.py` (Replicate)
- [ ] Implement `pipeline/proposal.py` (PDF)

### Phase 4 — Orchestration + Dashboard
- [ ] Implement `main.py` with APScheduler
- [ ] Implement Streamlit dashboard
- [ ] End-to-end test: full cycle from WhatsApp message to broker notification
- [ ] Load test: 100 messages, check classification accuracy

---

## ⚠️ IMPORTANT NOTES FOR CLAUDE CODE

1. **WhatsApp Web JS**: Session saved in `.wwebjs_auth/` — don't delete. Re-scan QR only if session expires.

2. **Group names in .env**: Must match EXACTLY as they appear in WhatsApp (Arabic included).

3. **Haiku for classification**: Use `claude-haiku-4-5-20251001` for classify/match (fast + cheap). Use `claude-sonnet-4-20250514` only for land analysis (vision).

4. **Existing scrapers**: Mr. Wolf has working Aqar.fm + Wasalt scrapers. Wrap them in `BaseSource` subclasses — don't rewrite from scratch.

5. **Privacy/Legal**: 
   - Contact info stored in local SQLite only
   - Never forwarded in automated messages
   - Broker is always the human decision-maker
   - Compliant with Saudi PDPL

6. **Rate limits**: Add `asyncio.sleep(1)` between Claude API calls in batch operations.

7. **Arabic in SQLite**: Always use `ensure_ascii=False` when storing JSON blobs.

8. **Saudi coverage**: All 15 regions listed in `TARGET_CITIES` — classifier will extract city from message text automatically.
