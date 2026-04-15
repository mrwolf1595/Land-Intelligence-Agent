# دليل النشر الكامل — Kali Linux
## Land Intelligence Agent

> **المتطلب الوحيد المفترض مسبقاً:** Ollama مثبت والموديلات موجودة على الجهاز.  
> كل شيء آخر موثق خطوة بخطوة أدناه.

---

## جدول المحتويات

1. [نظرة عامة على المعمارية](#1-نظرة-عامة)
2. [نقل المشروع من Windows إلى Kali](#2-نقل-المشروع)
3. [تثبيت متطلبات النظام](#3-متطلبات-النظام)
4. [إعداد Python Venv + المكتبات](#4-python-venv)
5. [إعداد Node.js (WhatsApp Bridge)](#5-nodejs)
6. [ملف الإعدادات `.env`](#6-ملف-env)
7. [تهيئة قاعدة البيانات](#7-قاعدة-البيانات)
8. [تشغيل الـ Scrapers](#8-تشغيل-scrapers)
9. [تشغيل WhatsApp Monitor](#9-whatsapp)
10. [تشغيل Dashboard](#10-dashboard)
11. [الوضع الكامل (Scheduled)](#11-الوضع-الكامل)
12. [تشغيل كـ Services في الخلفية (systemd / tmux)](#12-services)
13. [Geckodriver لـ Wasalt Selenium](#13-geckodriver)
14. [اختبار سريع للتحقق من كل شيء](#14-اختبار-سريع)
15. [حل المشاكل الشائعة](#15-حل-المشاكل)

---

## 1. نظرة عامة

```
┌─────────────────────────────────────────────────────────┐
│                    Land Intelligence Agent               │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │  Node.js     │───▶│  Python      │───▶│  Ollama   │  │
│  │  WhatsApp    │    │  Bridge      │    │  (local)  │  │
│  │  client.js   │    │  bridge.py   │    │  qwen2.5  │  │
│  │  :3001       │    │  :3002       │    │  :11434   │  │
│  └──────────────┘    └──────────────┘    └───────────┘  │
│                             │                            │
│  ┌──────────────┐    ┌──────▼───────┐                   │
│  │  Scrapers    │───▶│  SQLite DB   │───▶  Dashboard    │
│  │  (6 sources) │    │  db/agent.db │      :8501        │
│  └──────────────┘    └──────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

**المكونات:**
| المكون | المنفذ | الوصف |
|---|---|---|
| WhatsApp Node Client | 3001 | يراقب المجموعات ويستقبل الأوامر |
| Python FastAPI Bridge | 3002 | يصنف الرسائل ويحفظها في DB |
| Ollama | 11434 | الذكاء الاصطناعي المحلي |
| Streamlit Dashboard | 8501 | واجهة العرض للوسيط |
| SQLite DB | — | `db/agent.db` — كل البيانات |

---

## 2. نقل المشروع

### الطريقة الأولى: SCP من Windows (موصى بها)

على **Windows PowerShell** — شغّل هذا:
```powershell
# انقل المجلد كاملاً إلى Kali (عدّل IP حسب جهازك)
scp -r "K:\Projects\Land Intelligence Agent" kali@192.168.x.x:/opt/land-agent
```

> استبدل `192.168.x.x` بـ IP جهاز Kali.

### الطريقة الثانية: USB / مشاركة الشبكة

```bash
# بعد نسخ المجلد على Kali
sudo mv "/path/to/Land Intelligence Agent" /opt/land-agent
```

### الطريقة الثالثة: Git (إذا كان المشروع على GitHub)

```bash
git clone https://github.com/YOUR_USERNAME/land-agent.git /opt/land-agent
```

---

### بعد النقل — تحقق من المجلد

```bash
ls /opt/land-agent
# يجب أن يظهر:
# config.py  core/  dashboard/  db/  main.py  pipeline/
# requirements.txt  sources/  templates/  output/  package.json
```

**اجعل المشروع مجلدك الأساسي طوال الدليل:**

```bash
cd /opt/land-agent
# أو أضف هذا السطر في ~/.bashrc لتسهيل الوصول:
echo 'alias landagent="cd /opt/land-agent"' >> ~/.bashrc
```

---

## 3. متطلبات النظام

### 3.1 تحديث النظام أولاً

```bash
sudo apt update && sudo apt upgrade -y
```

### 3.2 Python 3.11+

```bash
# تحقق من الإصدار الحالي
python3 --version

# إذا كان أقل من 3.11:
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip
```

### 3.3 Node.js 18+

```bash
# تحقق من الإصدار الحالي
node --version

# إذا لم يكن مثبتاً أو إصداره قديم:
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# تحقق
node --version   # يجب >= 18
npm --version
```

### 3.4 مكتبات WeasyPrint (PDF Generator)

WeasyPrint تحتاج GTK — على Linux تعمل بشكل مثالي:

```bash
sudo apt install -y \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
    fonts-noto-core \
    fonts-noto-cjk
```

**دعم الخطوط العربية (مهم):**

```bash
sudo apt install -y \
    fonts-noto-color-emoji \
    fonts-arabeyes \
    fonts-hosny-amiri

# تحديث قائمة الخطوط
sudo fc-cache -fv
```

### 3.5 مكتبات Selenium / Firefox

```bash
# Firefox
sudo apt install -y firefox-esr

# تحقق
firefox --version
```

> سيُثبَّت geckodriver في [الخطوة 13](#13-geckodriver).

### 3.6 مكتبات أخرى

```bash
sudo apt install -y \
    libxml2-dev \
    libxslt1-dev \
    build-essential \
    curl \
    git
```

---

## 4. Python Venv

```bash
cd /opt/land-agent

# إنشاء البيئة الافتراضية
python3.11 -m venv .venv

# تفعيلها
source .venv/bin/activate

# تحديث pip
pip install --upgrade pip

# تثبيت كل المكتبات
pip install -r requirements.txt

# التحقق من النجاح
python -c "import ollama, httpx, fastapi, streamlit, cloudscraper, selenium; print('ALL OK')"
```

**الإخراج المتوقع:**
```
ALL OK
```

> **⚠️ تنبيه:** دائماً فعّل الـ venv قبل تشغيل أي أمر:
> ```bash
> source /opt/land-agent/.venv/bin/activate
> ```

### إضافة alias مريح في ~/.bashrc

```bash
echo 'alias la-activate="source /opt/land-agent/.venv/bin/activate && cd /opt/land-agent"' >> ~/.bashrc
source ~/.bashrc

# الآن يمكنك كتابة:
la-activate
```

---

## 5. Node.js

```bash
cd /opt/land-agent

# تثبيت المكتبات
npm install

# التحقق
node -e "require('whatsapp-web.js'); console.log('WhatsApp-web.js OK')"
```

**المكتبات التي ستُثبَّت:**
- `whatsapp-web.js` — الاتصال بـ WhatsApp
- `express` — HTTP server
- `axios` — إرسال الرسائل للـ Python
- `qrcode-terminal` — عرض QR في الطرفية
- `dotenv` — قراءة .env

---

## 6. ملف `.env`

```bash
cd /opt/land-agent

# انسخ القالب وعدّله
cp .env.example .env   # إذا وُجد
# أو أنشئه من الصفر:
nano .env
```

### المحتوى الكامل لـ `.env`

```dotenv
# ══════════════════════════════════════════
#   Land Intelligence Agent — إعدادات Kali
# ══════════════════════════════════════════

# ── Ollama (الذكاء الاصطناعي) ─────────────
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_MODEL_FAST=qwen2.5:3b

# ── WhatsApp ──────────────────────────────
# رقم هاتف الوسيط (بدون +) — يستقبل الإشعارات
BROKER_WHATSAPP=9665XXXXXXXX

# المجموعات التي سيراقبها الـ Agent (مطابقة جزئية للاسم)
WA_MONITORED_GROUPS=عقارات الرياض,أراضي جدة,وساطة عقارية

# منافذ التواصل الداخلي
WA_BRIDGE_PORT=3001
PYTHON_BRIDGE_PORT=3002

# ── فلاتر الأسعار (ريال سعودي) ────────────
PRICE_MIN_SAR=500000
PRICE_MAX_SAR=3750000

# ── المدن المستهدفة ───────────────────────
TARGET_CITIES=جدة,الرياض,الدمام,مكة,المدينة,الطائف,أبها,تبوك,القصيم,حائل,جازان,نجران,الجوف,الخبر,القطيف

# ── معايير التقييم ────────────────────────
MIN_MATCH_SCORE=0.65
MIN_OPPORTUNITY_SCORE=6.0

# ── مسارات SQLite القديمة (اختياري) ────────
# إذا عندك DB قديم من Aqar أو Wasalt
AQAR_DB_PATH=
WASALT_DB_PATH=

# ── تكاليف البناء (ريال/م²) ───────────────
CONSTRUCTION_COST_APARTMENTS=2200
CONSTRUCTION_COST_VILLAS=2800

# ── أسعار البيع المتوقعة (ريال/م²) ─────────
SELL_PRICE_APARTMENTS_SQM=6500
SELL_PRICE_VILLAS_SQM=5800

# ── تفعيل/تعطيل المميزات ──────────────────
FEATURE_WHATSAPP_MONITOR=true
FEATURE_PLATFORM_SCRAPING=true
FEATURE_AUTO_MATCH=true
FEATURE_PDF_PROPOSAL=true
FEATURE_AI_MOCKUP=false       # يحتاج ComfyUI — عطّله إذا غير متاح

# ── ComfyUI (اختياري) ─────────────────────
COMFYUI_API_URL=http://localhost:8188
SD_CHECKPOINT=v1-5-pruned-emaonly.ckpt
```

> **ملاحظات:**
> - `BROKER_WHATSAPP`: الرقم بدون `+` وبدون مسافات، مثال: `966501234567`
> - `WA_MONITORED_GROUPS`: أسماء جزئية — يكفي جزء من اسم المجموعة
> - `FEATURE_AI_MOCKUP=false` إذا لم يكن ComfyUI مثبتاً

---

## 7. قاعدة البيانات

```bash
cd /opt/land-agent
source .venv/bin/activate

# إنشاء الجداول وتهيئة DB
python -c "from core.database import init_db; init_db(); print('DB initialized OK')"
```

**ما سيُنشأ:**
```
db/
└── agent.db         ← SQLite database
    ├── messages      ← رسائل WhatsApp المصنفة
    ├── matches       ← تطابقات الطلب/العرض
    ├── opportunities ← إعلانات الأراضي المكتشفة
    └── scraper_cursors ← آخر run لكل منصة
```

---

## 8. تشغيل Scrapers

### اختبار سريع (One-shot)

```bash
cd /opt/land-agent
source .venv/bin/activate

python main.py --mode scrape
```

**سترى في الطرفية:**
```
[2026-04-15 14:00:01] INFO     config: Features مُفعَّلة: [platform_scraping, auto_match, ...]
[2026-04-15 14:00:02] INFO     aqar: Scraping 12 cities
[2026-04-15 14:00:05] INFO     aqar: الرياض page 0: 47 new listings
[2026-04-15 14:00:10] INFO     bayut: 23841 total listings across 239 pages
[2026-04-15 14:00:15] INFO     wasalt: Trying Selenium scraper...
...
[2026-04-15 14:15:00] INFO     main: DB [aqar]: 312 total | last: 2026-04-15 14:14
[2026-04-15 14:15:00] INFO     main: DB [bayut]: 1847 total | last: 2026-04-15 14:14
```

**وفي `logs/agent.log`** — نفس الإخراج محفوظ دائماً.

### تشغيل Scraper واحد فقط (للاختبار)

```bash
# تشغيل Aqar فقط
python -c "
from sources.aqar.scraper import Scraper
s = Scraper()
results = s.run()
print(f'Aqar: {len(results)} new listings')
"

# تشغيل Bayut فقط
python -c "
from sources.bayut.scraper import Scraper
s = Scraper()
results = s.run()
print(f'Bayut: {len(results)} new listings')
"
```

---

## 9. WhatsApp Monitor

### الخطوة 1 — تشغيل Node.js Client

```bash
cd /opt/land-agent

# في طرفية منفصلة (أو tmux)
node sources/whatsapp/client.js
```

**في أول تشغيل** ستظهر:
```
🔄 Initializing WhatsApp Client...

📱 Scan this QR code with your WhatsApp:
█████████████████████████████
█ ▄▄▄▄▄ █ ▄ █▄▀▄ █ ▄▄▄▄▄ █
█ █   █ █▀▄▀ ▄ ▀▄█ █   █ █
...
```

1. افتح **WhatsApp** على هاتفك
2. اذهب إلى **⋮ → الأجهزة المرتبطة → ربط جهاز**
3. امسح QR Code الظاهر في الطرفية
4. بعد النجاح ستظهر: `✅ WhatsApp connected successfully`

> **مهم:** بعد أول اتصال تُحفظ الجلسة في `.wwebjs_auth/` ولن تحتاج QR مرة أخرى.

### الخطوة 2 — تشغيل Python Bridge

```bash
# في طرفية ثانية
cd /opt/land-agent
source .venv/bin/activate

uvicorn sources.whatsapp.bridge:app --host 0.0.0.0 --port 3002 --log-level info
```

### التحقق من الاتصال

```bash
# تحقق من Python Bridge
curl http://localhost:3002/health
# {"status": "ok", "service": "whatsapp-bridge"}

# تحقق من Node Bridge
curl http://localhost:3001/status
# {"connected": true, "groups": ["عقارات الرياض", ...]}
```

---

## 10. Dashboard

```bash
cd /opt/land-agent
source .venv/bin/activate

streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0
```

افتح المتصفح على: **`http://localhost:8501`**

أو إذا أردت الوصول من جهاز آخر على الشبكة:
```
http://KALI_IP:8501
```

**التبويبات المتاحة:**
- 🔗 **تطابقات جديدة** — طلبات تطابقت مع عروض، بانتظار قرارك
- 🏗️ **فرص الأراضي** — إعلانات تم تحليلها بـ Ollama مع ROI
- 📊 **إحصائيات** — أرقام إجمالية + حالة كل scraper

---

## 11. الوضع الكامل (Scheduled)

يشغّل كل شيء تلقائياً: Matching كل دقيقتين + Scraping كل ساعة.

```bash
cd /opt/land-agent
source .venv/bin/activate

python main.py
# أو حدد وضعاً:
python main.py --mode all
```

**الأوضاع المتاحة:**

| الأمر | الوصف |
|---|---|
| `python main.py` | الوضع الكامل المجدول |
| `python main.py --mode scrape` | تشغيل واحد للـ scrapers |
| `python main.py --mode match` | تشغيل واحد للـ matching |
| `python main.py --mode monitor` | WhatsApp فقط (بدون scraping) |

---

## 12. Services في الخلفية

### الطريقة الأولى: tmux (الأسهل)

```bash
# تثبيت tmux
sudo apt install -y tmux

# إنشاء session
tmux new-session -s land-agent

# داخل tmux — قسّم النوافذ:
# نافذة 1: Node.js WhatsApp
tmux new-window -t land-agent -n "whatsapp"
tmux send-keys -t land-agent:whatsapp "cd /opt/land-agent && node sources/whatsapp/client.js" Enter

# نافذة 2: Python Bridge
tmux new-window -t land-agent -n "bridge"
tmux send-keys -t land-agent:bridge "cd /opt/land-agent && source .venv/bin/activate && uvicorn sources.whatsapp.bridge:app --port 3002" Enter

# نافذة 3: Agent الرئيسي
tmux new-window -t land-agent -n "agent"
tmux send-keys -t land-agent:agent "cd /opt/land-agent && source .venv/bin/activate && python main.py" Enter

# نافذة 4: Dashboard
tmux new-window -t land-agent -n "dashboard"
tmux send-keys -t land-agent:dashboard "cd /opt/land-agent && source .venv/bin/activate && streamlit run dashboard/app.py --server.port 8501" Enter

# اخرج من tmux (تبقى تعمل في الخلفية)
# اضغط: Ctrl+B ثم D

# للعودة إليها لاحقاً:
tmux attach -t land-agent
```

---

### الطريقة الثانية: systemd Services (للإنتاج الدائم)

#### ملف Service 1: Python Agent

```bash
sudo nano /etc/systemd/system/land-agent.service
```

```ini
[Unit]
Description=Land Intelligence Agent (Python)
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=kali
WorkingDirectory=/opt/land-agent
ExecStart=/opt/land-agent/.venv/bin/python main.py
Restart=on-failure
RestartSec=10s
StandardOutput=append:/opt/land-agent/logs/agent.log
StandardError=append:/opt/land-agent/logs/agent.log
EnvironmentFile=/opt/land-agent/.env

[Install]
WantedBy=multi-user.target
```

#### ملف Service 2: Node.js WhatsApp

```bash
sudo nano /etc/systemd/system/land-agent-whatsapp.service
```

```ini
[Unit]
Description=Land Agent WhatsApp Node.js Bridge
After=network.target

[Service]
Type=simple
User=kali
WorkingDirectory=/opt/land-agent
ExecStart=/usr/bin/node sources/whatsapp/client.js
Restart=on-failure
RestartSec=15s
StandardOutput=append:/opt/land-agent/logs/whatsapp.log
StandardError=append:/opt/land-agent/logs/whatsapp.log
EnvironmentFile=/opt/land-agent/.env

[Install]
WantedBy=multi-user.target
```

#### ملف Service 3: Dashboard

```bash
sudo nano /etc/systemd/system/land-agent-dashboard.service
```

```ini
[Unit]
Description=Land Agent Streamlit Dashboard
After=network.target

[Service]
Type=simple
User=kali
WorkingDirectory=/opt/land-agent
ExecStart=/opt/land-agent/.venv/bin/streamlit run dashboard/app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=on-failure
RestartSec=5s
EnvironmentFile=/opt/land-agent/.env

[Install]
WantedBy=multi-user.target
```

#### تفعيل وتشغيل الـ Services

```bash
# تحميل ملفات الـ services
sudo systemctl daemon-reload

# تفعيل التشغيل التلقائي عند الإقلاع
sudo systemctl enable land-agent
sudo systemctl enable land-agent-whatsapp
sudo systemctl enable land-agent-dashboard

# تشغيل الآن
sudo systemctl start land-agent-whatsapp
sleep 5   # انتظر WhatsApp يتهيأ
sudo systemctl start land-agent
sudo systemctl start land-agent-dashboard

# التحقق من الحالة
sudo systemctl status land-agent
sudo systemctl status land-agent-whatsapp
sudo systemctl status land-agent-dashboard
```

#### أوامر إدارة الـ Services

```bash
# إيقاف
sudo systemctl stop land-agent

# إعادة تشغيل
sudo systemctl restart land-agent

# مشاهدة الـ logs
sudo journalctl -u land-agent -f
# أو مباشرة:
tail -f /opt/land-agent/logs/agent.log
```

---

## 13. Geckodriver (Wasalt Selenium)

Geckodriver مطلوب فقط لـ Wasalt — إذا فشل الـ HTTP scraper (403).

```bash
# تحقق من إصدار Firefox
firefox --version
# مثال: Mozilla Firefox 115.0

# حمّل geckodriver المناسب من GitHub
# اذهب إلى: https://github.com/mozilla/geckodriver/releases
# اختر: geckodriver-v0.35.0-linux64.tar.gz

# تثبيت تلقائي (يختار الإصدار الأحدث):
GECKO_VER=$(curl -s https://api.github.com/repos/mozilla/geckodriver/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
curl -fsSL "https://github.com/mozilla/geckodriver/releases/download/${GECKO_VER}/geckodriver-${GECKO_VER}-linux64.tar.gz" -o /tmp/geckodriver.tar.gz
tar -xzf /tmp/geckodriver.tar.gz -C /tmp/
sudo mv /tmp/geckodriver /usr/local/bin/geckodriver
sudo chmod +x /usr/local/bin/geckodriver

# التحقق
geckodriver --version
# geckodriver 0.35.0 (...)
```

> الـ scraper يبحث عن geckodriver في `/usr/local/bin/geckodriver` — هذا هو المسار المحدد في الكود.

**اختبار Selenium:**

```bash
cd /opt/land-agent
source .venv/bin/activate

python -c "
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

opts = Options()
opts.add_argument('--headless')
driver = webdriver.Firefox(service=Service('/usr/local/bin/geckodriver'), options=opts)
driver.get('https://wasalt.sa')
print('Title:', driver.title[:50])
driver.quit()
print('Selenium OK')
"
```

---

## 14. اختبار سريع — تحقق من كل شيء

```bash
cd /opt/land-agent
source .venv/bin/activate

python -c "
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
print('='*50)
print('Land Agent — System Check')
print('='*50)

# 1. Core modules
mods = ['core.logger','core.scheduler','core.database','config']
for m in mods:
    try: __import__(m); print(f'  OK  {m}')
    except Exception as e: print(f'  FAIL {m}: {e}')

# 2. Pipeline
mods = ['pipeline.classifier','pipeline.matcher','pipeline.analyzer',
        'pipeline.notifier','pipeline.financial','pipeline.proposal']
for m in mods:
    try: __import__(m); print(f'  OK  {m}')
    except Exception as e: print(f'  FAIL {m}: {e}')

# 3. Scrapers
scrapers = ['aqar','bayut','wasalt','propertyfinder','sakan','haraj']
for s in scrapers:
    try:
        m = __import__(f'sources.{s}.scraper', fromlist=['Scraper'])
        print(f'  OK  scraper:{s}')
    except Exception as e: print(f'  FAIL scraper:{s}: {e}')

# 4. Database
from core.database import init_db
init_db()
print('  OK  database init')

# 5. Ollama connectivity
import httpx
try:
    r = httpx.get('http://localhost:11434/api/tags', timeout=3)
    models = [m['name'] for m in r.json().get('models',[])]
    print(f'  OK  Ollama ({len(models)} models: {models[:3]})')
except:
    print('  WARN Ollama not reachable (start with: ollama serve)')

print('='*50)
print('Done. Check WARNs/FAILs above.')
"
```

**الإخراج المتوقع:**
```
==================================================
Land Agent — System Check
==================================================
  OK  core.logger
  OK  core.scheduler
  OK  core.database
  OK  config
  OK  pipeline.classifier
  ...
  OK  scraper:aqar
  OK  scraper:bayut
  OK  scraper:wasalt
  OK  scraper:propertyfinder
  OK  scraper:sakan
  OK  scraper:haraj
  OK  database init
  OK  Ollama (3 models: ['qwen2.5:7b', 'qwen2.5:3b', ...])
==================================================
```

---

## 15. حل المشاكل الشائعة

### ❌ `ModuleNotFoundError: No module named 'ollama'`
```bash
source /opt/land-agent/.venv/bin/activate
pip install -r requirements.txt
```

### ❌ `Connection refused` من Ollama
```bash
# تأكد أن Ollama يعمل
ollama serve &

# تحقق
curl http://localhost:11434/api/tags

# تأكد من وجود الموديلات
ollama list
```

### ❌ WeasyPrint لا تولّد PDF
```bash
# تثبيت مكتبات GTK
sudo apt install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0

# اختبار
python -c "from weasyprint import HTML; HTML(string='<h1>Test</h1>').write_pdf('/tmp/test.pdf'); print('PDF OK')"
```

### ❌ `cloudscraper` مشكلة مع Aqar
```bash
# تحديث cloudscraper
pip install --upgrade cloudscraper

# اختبار مباشر
python -c "
import cloudscraper
s = cloudscraper.create_scraper()
r = s.post('https://sa.aqar.fm/graphql', json={'query':'{ __typename }'}, timeout=10)
print(r.status_code, r.text[:100])
"
```

### ❌ Wasalt يعطي 403 باستمرار
```bash
# تأكد من تثبيت geckodriver
geckodriver --version

# اختبار Selenium مباشرة
python -c "
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
opts = Options(); opts.add_argument('--headless')
d = webdriver.Firefox(options=opts)
d.get('https://wasalt.sa/sale/search?page=0')
has_data = '__NEXT_DATA__' in d.page_source
d.quit()
print('Selenium Wasalt:', 'OK' if has_data else 'No data')
"
```

### ❌ WhatsApp QR لا يعمل
```bash
# احذف جلسة قديمة وأعد المحاولة
rm -rf /opt/land-agent/.wwebjs_auth
cd /opt/land-agent
node sources/whatsapp/client.js
```

### ❌ الـ Dashboard لا يفتح
```bash
# تأكد أن المنفذ 8501 غير مشغول
ss -tlnp | grep 8501

# تشغيل على منفذ مختلف
streamlit run dashboard/app.py --server.port 8502
```

### ❌ خطأ في قاعدة البيانات `no such column`
```bash
# أعد تهيئة DB (تضيف الأعمدة الناقصة)
python -c "from core.database import init_db; init_db(); print('Migration done')"
```

### 📋 مراجعة الـ Logs

```bash
# Log الـ agent الرئيسي
tail -f /opt/land-agent/logs/agent.log

# فلترة الأخطاء فقط
grep ERROR /opt/land-agent/logs/agent.log | tail -20

# فلترة scraper معين
grep "\[aqar\]" /opt/land-agent/logs/agent.log | tail -20
```

---

## ملخص أوامر التشغيل اليومي

```bash
# ─── تفعيل البيئة ────────────────────────
cd /opt/land-agent && source .venv/bin/activate

# ─── تشغيل Scraping فقط ──────────────────
python main.py --mode scrape

# ─── تشغيل Matching فقط ──────────────────
python main.py --mode match

# ─── WhatsApp فقط (بدون scraping) ─────────
python main.py --mode monitor

# ─── الوضع الكامل ─────────────────────────
python main.py

# ─── Dashboard ───────────────────────────
streamlit run dashboard/app.py

# ─── مشاهدة الـ logs ──────────────────────
tail -f logs/agent.log
```

---

## 16. رفع المشروع على GitHub (Push آمن)

هذه الخطوة مهمة إذا أردت نقل آخر نسخة من المشروع إلى GitHub بدون رفع ملفات حساسة أو ملفات جلسات WhatsApp.

### 16.1 تأكد من الفرع الحالي والـ remote

```bash
cd /opt/land-agent
git branch --show-current
git remote -v
```

إذا لم يكن هناك remote:

```bash
git remote add origin https://github.com/mrwolf1595/Land-Intelligence-Agent.git
```

### 16.2 استبعد ملفات الجلسات والحالة المحلية قبل الرفع

أضف هذه الأسطر إلى `.gitignore` إن لم تكن موجودة:

```gitignore
.wwebjs_auth/
.claude/
.env
logs/
db/*.db
__pycache__/
*.pyc
```

ثم أزلها من الـ index إذا كانت مضافة سابقاً:

```bash
git rm -r --cached .wwebjs_auth .claude .env logs db/*.db 2>/dev/null || true
```

### 16.3 إنشاء commit جديد

```bash
git add -A
git commit -m "chore: update deployment guide and prepare clean production push"
```

إذا ظهر: `nothing to commit` فهذا طبيعي.

### 16.4 رفع الفرع إلى GitHub

المستودع يستخدم `main` كفرع افتراضي. إذا كنت على `master`:

```bash
git push -u origin master:main
```

بعد أول مرة، يمكنك لاحقاً الرفع مباشرة:

```bash
git push
```

### 16.5 التحقق بعد الرفع

```bash
git log --oneline -n 5
git status
```

ثم افتح:

`https://github.com/mrwolf1595/Land-Intelligence-Agent`

وتأكد أن آخر commit ظاهر على فرع `main`.

---

## 17. Checklist قبل أي نشر إنتاجي

نفّذ هذه القائمة بسرعة قبل تشغيل النظام 24/7:

- [ ] ملف `.env` مضبوط (الرقم، المدن، الميزات)
- [ ] `python -c "from core.database import init_db; init_db()"` يعمل بدون أخطاء
- [ ] `pytest tests/test_smoke.py -v` ناجح
- [ ] `curl http://localhost:11434/api/tags` يعيد موديلات Ollama
- [ ] `node sources/whatsapp/client.js` متصل وQR ممسوح
- [ ] `streamlit run dashboard/app.py` يفتح بدون أخطاء
- [ ] لا توجد أسرار أو جلسات ضمن الملفات المرفوعة على GitHub

---

*آخر تحديث: 2026-04-15 — Session 4*
