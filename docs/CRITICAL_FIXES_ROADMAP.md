# 🚨 خارطة الإصلاح الشامل — من نظام حسابي إلى Agent يُعتمد عليه

> **تاريخ التقييم:** 2026-04-17  
> **الحالة:** المشروع يملك بنية هندسية ممتازة، لكنه يعمل في **فراغ بياني**.  
> القرارات المالية تخرج بناءً على معادلات صحيحة لكن بأرقام وهمية — مثل نظام ملاحي دقيق بخريطة غير محدثة.

---

## 📊 ملخص التقييم

| المعيار | الدرجة | التعليق |
|---------|--------|---------|
| البنية الهندسية | 8/10 | ممتاز — الكود منظم وقابل للتوسع |
| جودة الكود | 7/10 | جيد جداً — pipeline واضح ومنطقي |
| **دقة البيانات** | **3/10** | **المشكلة الأكبر — الأرقام المرجعية وهمية** |
| **موثوقية التحليل** | **4/10** | **ضعيف — مبني على بيانات ثابتة من 2022** |
| واجهة القرار | 5/10 | متوسط — CFO data مبني لكن مخفي |
| الحماية من الخسارة | 6/10 | جيد — red flags موجودة |
| **قابلية الاعتماد** | **4/10** | **لسه مش agent حقيقي** |

---

## 🔴 المشاكل الجوهرية المكتشفة

### المشكلة 1 — البيانات المرجعية خيالية (الأخطر)

الكود الحالي في `config.py`:
```python
CONSTRUCTION_COST_APARTMENTS = 2200   # SAR/m² — رقم من 2022
SELL_PRICE_APARTMENTS_SQM    = 6500   # SAR/m² — رقم عام مبهم
DYNAMIC_SIBOR_RATE           = 0.055  # placeholder لم يُربط بأي API
```
كل حسبة ROI و IRR و Breakeven تبنى فوق هذه الأرقام الثابتة.

### المشكلة 2 — price_benchmarks تسأل نفسها

`benchmarks.py` يحسب متوسط السوق من نفس الـ listings التي يسكريبها.  
إذا جاءت listings مبالغ فيها → benchmark مرتفع → الأرض الغالية تبدو "رخيصة نسبياً" → score عالي خاطئ.

### المشكلة 3 — Haraj price = None دائماً

Haraj أكبر مصدر لأراضي الأفراد بأسعار واقعية — لكن `price_sar` دائماً `None`.  
يعني كل الإحصاء والـ benchmark لا يستفيد من Haraj أبداً.

### المشكلة 4 — qwen2.5:7b لا يعرف السوق السعودي

الموديل لا يعرف أسعار الأحياء، ولا لوائح البناء، ولا إن الحي مكتظ أم لا.  
الـ Fallback rule-based يشتغل معظم الوقت — يعني Ollama لا يضيف قيمة حقيقية.

### المشكلة 5 — cfo_manager.py غير مربوط بالـ Dashboard

IRR، Wafi analysis، cashflow timing — كلها مبنية لكن لا تظهر للمستخدم.  
ما يُعرض فقط: ROI% من 3 سيناريوهات + breakeven price.

### المشكلة 6 — لا توجد حماية من الاستملاك الحكومي

`data/expropriation_zones.json` موجود لكن غير محدث بمشاريع Vision 2030 الفعلية.  
أرض في مسار نيوم أو مشروع حكومي = استملاك بـ 30-50% من السوق — خسارة وجودية.

### المشكلة 7 — لا يوجد Absorption Rate

النظام يفترض "بيعت كل الوحدات" — لكن لا يتحقق:
- هل السوق في هذا الحي يستوعب عمارة جديدة؟
- هل الأراضي المعروضة من قبل اتباعت أم لسه موجودة بعد 90 يوم؟

### المشكلة 8 — لا تحقق قانوني من رقم الصك

النظام يبحث عن كلمة "نزاع" في النص فقط.  
لا يوجد تحقق من رقم الصك عبر نافذة أو Wathiq أو أي مصدر رسمي.

---

## 🛠️ خارطة الإصلاح — خطوة بخطوة

---

## PHASE 1 — إصلاح جودة البيانات (الأعلى أولوية)

> **الهدف:** بيانات حقيقية قبل أي تحليل.

---

### الخطوة 1.1 — إصلاح Haraj price extraction

**الملف:** `sources/haraj/scraper.py` → دالة `normalize()`

**المشكلة:** `price` field من API دائماً `None`. السعر مدفون في `bodyTEXT` كنص عربي.

**أمثلة من بيانات حقيقية:**
```
"السعر: 960,000 ريال"
"سعر الارض 1.5 مليون"
"المساحة 312 م سعر الوحدة 7 آلاف"
"ب 850 الف"
```

**الحل — أضف الدالتين التاليتين:**

```python
import re

def _price_from_text(text: str) -> float | None:
    """استخراج السعر من النص العربي بأنماط متعددة."""
    if not text:
        return None
    text = text.replace(",", "").replace("،", "")
    
    # نمط "X مليون" أو "X.X مليون"
    m = re.search(r"([\d\.]+)\s*مليون", text)
    if m:
        return float(m.group(1)) * 1_000_000
    
    # نمط "X ألف" أو "X آلاف"
    m = re.search(r"([\d\.]+)\s*(?:ألف|آلاف)", text)
    if m:
        return float(m.group(1)) * 1_000
    
    # نمط "السعر: X" أو "سعر الارض X"
    m = re.search(r"(?:السعر|سعر[^::\d]*)\s*[:：]?\s*([\d]+)", text)
    if m and len(m.group(1)) >= 4:
        return float(m.group(1))
    
    # نمط "X ريال" — أخذ أكبر رقم
    matches = re.findall(r"([\d]{4,})\s*(?:ريال|SAR)?", text)
    if matches:
        return max(float(v) for v in matches)
    
    return None

def _area_from_text(text: str) -> float | None:
    """استخراج المساحة من النص العربي."""
    if not text:
        return None
    text = text.replace(",", "")
    m = re.search(r"([\d\.]+)\s*(?:م²|م2|متر|م\b)", text)
    return float(m.group(1)) if m else None
```

**في `normalize()`:**
```python
price = raw.get("price") or _price_from_text(raw.get("bodyTEXT", ""))
area  = raw.get("area") or _area_from_text(raw.get("bodyTEXT", ""))
```

**اختبار الصحة:**
```bash
python -c "
import sys; sys.path.insert(0,'.')
from sources.haraj.scraper import Scraper
items = Scraper().fetch()
with_price = [i for i in items if i.get('price') and i['price'] > 0]
print(f'السعر موجود في {len(with_price)}/{len(items)} listing')
print(with_price[:2])
"
```
**الهدف:** `> 50%` من listings فيها سعر.

**بعد الاختبار:** `git commit -m "fix: haraj price extraction from bodyTEXT"`

---

### الخطوة 1.2 — التأكد من أن MOJ scraper يعمل فعلاً

**الملف:** `sources/moj/scraper.py`

**المشكلة:** الملف موجود لكن غير معروف إذا كان يجيب بيانات حقيقية.

**خطوات التحقق:**
```bash
python -c "
import sys; sys.path.insert(0,'.')
from sources.moj.scraper import Scraper
s = Scraper()
results = s.fetch()
print(f'MOJ returned {len(results)} records')
if results:
    print(results[0])
"
```

**إذا رجع 0 نتائج أو خطأ:**
- افتح `sources/moj/scraper.py` واقرأ الـ endpoints المستخدمة
- اعمل `curl` يدوي على الـ URL لترى هل لا يزال يستجيب
- إذا تغير الـ API، ابحث عن البديل في `srem.moj.gov.sa`

**إذا يعمل — فعّل الربط بالـ benchmark:**

في `pipeline/benchmarks.py`، اجعل `rebuild_benchmarks()` تدمج بيانات MOJ:
```python
def rebuild_benchmarks():
    # 1. احسب المتوسط من listings المسكريبة (50% وزن)
    scraped_avg = _calc_from_opportunities(conn)
    
    # 2. احضر من MOJ إذا متاح (50% وزن)
    moj_avg = _calc_from_moj(conn)  # جدول منفصل moj_transactions
    
    # 3. ادمج
    if moj_avg and scraped_avg:
        final_avg = (scraped_avg * 0.5) + (moj_avg * 0.5)
    elif moj_avg:
        final_avg = moj_avg
    else:
        final_avg = scraped_avg
```

**بعد الاختبار:** `git commit -m "fix: verify and activate MOJ scraper integration"`

---

### الخطوة 1.3 — فصل benchmark عن بيانات الـ scraping

**المشكلة الجوهرية:** `benchmarks.py` يسأل نفسه — يحسب "سعر السوق" من نفس listings المسكريبة.

**الحل في `core/database.py`، أضف جدول منفصل:**
```sql
CREATE TABLE IF NOT EXISTS market_reference_prices (
    city TEXT NOT NULL,
    district TEXT NOT NULL DEFAULT '',
    price_per_sqm REAL NOT NULL,
    source TEXT NOT NULL,          -- 'moj' | 'manual' | 'ejar'
    transaction_date TEXT,
    sample_count INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (city, district, source)
);
```

**في `benchmarks.py`، اجعل `get_benchmark()` يفضّل هذا الجدول:**
```python
def get_benchmark(city: str, district: str = "") -> dict | None:
    # أولاً: ابحث في بيانات المرجعية المستقلة
    ref = conn.execute("""
        SELECT AVG(price_per_sqm), COUNT(*)
        FROM market_reference_prices
        WHERE city = ? AND district = ?
    """, (city, district)).fetchone()
    
    if ref and ref[1] >= 2:
        return {"avg": ref[0], "median": ref[0], "count": ref[1], "source": "reference"}
    
    # ثانياً: fallback للبيانات المسكريبة (مع تحذير)
    scraped = conn.execute("""
        SELECT AVG(price_sar/area_sqm), COUNT(*)
        FROM opportunities
        WHERE city=? AND district=? AND price_sar>0 AND area_sqm>0
        AND duplicate_of IS NULL
    """, (city, district)).fetchone()
    
    if scraped and scraped[1] >= 5:
        return {"avg": scraped[0], "median": scraped[0], "count": scraped[1], "source": "scraped"}
    
    return None
```

> **ملاحظة:** إذا `source == "scraped"` → confidence يبقى LOW حتى لو sample كبير.

**بعد الاختبار:** `git commit -m "feat: separate reference prices from scraped benchmark"`

---

### الخطوة 1.4 — Cross-platform deduplication

**الملفات:** `core/database.py`، ملف جديد `core/dedup.py`

**Migration في `_ensure_tables()`:**
```python
try:
    conn.execute("ALTER TABLE opportunities ADD COLUMN duplicate_of TEXT DEFAULT NULL")
    conn.commit()
except Exception:
    pass  # العمود موجود بالفعل
```

**`core/dedup.py`:**
```python
def find_duplicate(listing: dict, conn) -> str | None:
    """إيجاد listing مكرر بنفس المدينة والمساحة والسعر تقريباً."""
    city  = listing.get("city", "")
    area  = float(listing.get("area_sqm") or 0)
    price = float(listing.get("price_sar") or 0)
    lid   = listing.get("listing_id", "")
    
    if not city or area <= 0 or price <= 0:
        return None
    
    rows = conn.execute("""
        SELECT listing_id, area_sqm, price_sar FROM opportunities
        WHERE city = ? AND duplicate_of IS NULL AND listing_id != ?
    """, (city, lid)).fetchall()
    
    for row in rows:
        if row[1] and row[2]:
            area_diff  = abs(row[1] - area)  / area
            price_diff = abs(row[2] - price) / price
            if area_diff < 0.05 and price_diff < 0.10:
                return row[0]  # هذا هو الـ ID الأصلي
    return None

def mark_duplicates(conn) -> int:
    """تشغيل بعد كل دورة scraping لتصنيف المكررات."""
    rows = conn.execute("""
        SELECT listing_id, city, area_sqm, price_sar
        FROM opportunities WHERE duplicate_of IS NULL
        ORDER BY scraped_at DESC LIMIT 500
    """).fetchall()
    
    marked = 0
    for row in rows:
        dup = find_duplicate({
            "listing_id": row[0], "city": row[1],
            "area_sqm": row[2], "price_sar": row[3]
        }, conn)
        if dup:
            conn.execute(
                "UPDATE opportunities SET duplicate_of=? WHERE listing_id=?",
                (dup, row[0])
            )
            marked += 1
    conn.commit()
    return marked
```

**في `main.py` بعد كل دورة scraping:**
```python
from core.dedup import mark_duplicates
marked = mark_duplicates(conn)
logger.info(f"Marked {marked} duplicates this cycle")
```

**في Dashboard — أضف فلتر:**
```python
WHERE duplicate_of IS NULL  # في كل queries الـ dashboard
```

**بعد الاختبار:** `git commit -m "feat: cross-platform deduplication engine"`

---

## PHASE 2 — إصلاح دقة التحليل المالي

> **الهدف:** أرقام حقيقية تعكس السوق الحالي.

---

### الخطوة 2.1 — ربط تكلفة البناء بمؤشر GASTAT

**الملف الجديد:** `pipeline/market_rates.py`

```python
"""
مؤشرات السوق الديناميكية — يتم التحديث من مصادر خارجية.
في حال فشل الاتحاد بالمصادر، يُستخدم آخر قيمة محفوظة في DB.
"""
import httpx
from core.database import get_connection
from config import CONSTRUCTION_COST_APARTMENTS, CONSTRUCTION_COST_VILLAS

def get_construction_cost(dev_type: str = "apartments") -> float:
    """
    إرجاع تكلفة البناء الحالية لكل م².
    يحاول GASTAT أولاً، ثم DB cache، ثم config fallback.
    """
    cached = _get_cached_rate(f"construction_{dev_type}")
    if cached:
        return cached
    
    # fallback للقيم الثابتة في config
    defaults = {
        "apartments": CONSTRUCTION_COST_APARTMENTS,
        "villas":     CONSTRUCTION_COST_VILLAS,
        "commercial": 3000,
    }
    return defaults.get(dev_type, 2200)

def get_sibor_rate() -> float:
    """
    إرجاع معدل السايبور الحالي.
    يحاول SAMA API أولاً، ثم DB cache، ثم 7% fallback.
    """
    cached = _get_cached_rate("sibor_rate")
    if cached:
        return cached
    
    # TODO: ربط بـ SAMA API الرسمي
    # https://www.sama.gov.sa/en-US/EconomicReports/Pages/MonthlyStatistics.aspx
    return 0.07  # fallback

def _get_cached_rate(key: str) -> float | None:
    """قراءة آخر قيمة مخزنة في DB (صالحة لـ 30 يوم)."""
    try:
        with get_connection() as conn:
            row = conn.execute("""
                SELECT value FROM market_rates
                WHERE rate_key = ?
                AND datetime(updated_at) > datetime('now', '-30 days')
            """, (key,)).fetchone()
            return float(row[0]) if row else None
    except Exception:
        return None

def update_rate(key: str, value: float):
    """تحديث قيمة في الـ cache."""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO market_rates (rate_key, value, updated_at)
            VALUES (?, ?, datetime('now'))
        """, (key, value))
        conn.commit()
```

**Migration — أضف جدول في `_ensure_tables()`:**
```sql
CREATE TABLE IF NOT EXISTS market_rates (
    rate_key   TEXT PRIMARY KEY,
    value      REAL NOT NULL,
    updated_at TEXT NOT NULL
);
```

**في `pipeline/financial.py`، استبدل:**
```python
# قبل:
cost_per_sqm = CONSTRUCTION_COST_APARTMENTS

# بعد:
from pipeline.market_rates import get_construction_cost, get_sibor_rate
cost_per_sqm = get_construction_cost(dev_type)
interest_rate = get_sibor_rate()
```

**بعد الاختبار:** `git commit -m "feat: dynamic construction cost and SIBOR via market_rates"`

---

### الخطوة 2.2 — إصلاح scoring ليعتمد على البنشمارك المستقل

**الملف:** `pipeline/analyzer.py` → `_rule_based_score()`

**الكود الحالي يستخدم benchmark من نفس الـ scraping data.**  
بعد الخطوة 1.3، البنشمارك المستقل متاح — استخدمه:

```python
from pipeline.benchmarks import get_benchmark

def _rule_based_score(listing_data: dict) -> float:
    score = 0.0
    price_sar = float(listing_data.get("price_sar") or 0)
    area_sqm  = float(listing_data.get("area_sqm") or 0)
    city      = listing_data.get("city", "")
    district  = listing_data.get("district", "")
    price_sqm = price_sar / area_sqm if area_sqm > 0 else 0

    bench = get_benchmark(city, district) or get_benchmark(city, "")
    
    if bench and bench.get("source") == "reference" and bench["count"] >= 3 and price_sqm > 0:
        # بنشمارك مستقل من MOJ أو مصدر خارجي — نثق به
        ratio = price_sqm / bench["avg"]
        if ratio < 0.75:   score += 4.0   # أرخص من السوق بـ 25%+
        elif ratio < 0.90: score += 3.0   # أرخص بـ 10-25%
        elif ratio < 1.00: score += 1.5   # أقل بقليل من السوق
        elif ratio < 1.10: score += 0.5   # عند متوسط السوق
        else:              score -= 1.0   # فوق السوق
    elif bench and bench.get("source") == "scraped" and bench["count"] >= 10:
        # بيانات مسكريبة — ثقة أقل، وزن أقل
        ratio = price_sqm / bench["avg"]
        if ratio < 0.75:   score += 2.5
        elif ratio < 0.90: score += 1.5
        elif ratio < 1.00: score += 0.5
    else:
        # لا يوجد بنشمارك — اعتمد على المساحة فقط
        if area_sqm >= 600:  score += 2.0
        elif area_sqm >= 300: score += 1.0

    if listing_data.get("contact_phone"):  score += 1.0
    PREMIUM = {"الرياض", "جدة", "مكة المكرمة", "المدينة المنورة"}
    if city in PREMIUM:                    score += 1.0
    if 100_000 <= price_sar <= 50_000_000: score += 1.0

    return min(max(score, 0.0), 10.0)
```

**بعد الاختبار:** `git commit -m "fix: scoring uses independent benchmark source with confidence weighting"`

---

### الخطوة 2.3 — إضافة سيناريو الإيجار (Build & Hold)

**الملف:** `pipeline/financial.py`

**المشكلة:** النظام الحالي يفترض "بيع فوري" فقط. لكن الإيجار قد يكون أفضل ماليًا.

**أضف سيناريو رابع:**
```python
def calculate_rental_scenario(listing_data: dict, build_cost: float) -> dict:
    """
    سيناريو: بناء عمارة وتأجيرها بدلاً من البيع.
    يستخدم بيانات Ejar إذا متاحة، وإلا معدل 7% سنوي.
    """
    area_sqm      = float(listing_data.get("area_sqm") or 0)
    far           = listing_data.get("far", 2.0)
    buildable     = area_sqm * far
    
    # معدل الإيجار من Ejar أو fallback
    rental_yield  = _get_ejar_yield(listing_data.get("city"), listing_data.get("district"))
    if not rental_yield:
        rental_yield = 0.07  # 7% سنوياً fallback
    
    land_cost      = float(listing_data.get("price_sar") or 0)
    total_invest   = land_cost + build_cost
    annual_revenue = total_invest * rental_yield
    monthly_rev    = annual_revenue / 12
    
    # سنوات استرداد رأس المال
    payback_years  = total_invest / annual_revenue if annual_revenue > 0 else 999
    
    return {
        "scenario": "rental",
        "annual_revenue_sar":   round(annual_revenue),
        "monthly_revenue_sar":  round(monthly_rev),
        "rental_yield_pct":     round(rental_yield * 100, 1),
        "payback_years":        round(payback_years, 1),
        "total_investment_sar": round(total_invest),
        "vs_sell_advantage":    None,  # يتحدد بالمقارنة مع expected ROI
    }
```

**في Dashboard — أضف مقارنة:**
```
💰 البيع الجاهز: ROI 35% خلال 24 شهر
🏠 الإيجار:     عائد 7% سنوياً | استرداد 14 سنة | دخل شهري 18,500 ر.س
```

**بعد الاختبار:** `git commit -m "feat: rental scenario (build & hold) alongside sell scenarios"`

---

## PHASE 3 — حماية من مخاطر مميتة

> **الهدف:** منع الكارثة قبل أن تبدأ.

---

### الخطوة 3.1 — قاعدة بيانات مناطق الاستملاك

**الملف:** `data/expropriation_zones.json` (موجود لكن يحتاج تحديث)

**التنسيق المطلوب:**
```json
[
  {
    "name": "مشروع نيوم",
    "type": "megaproject",
    "cities": ["تبوك", "حقل", "شرما"],
    "risk_level": "CRITICAL",
    "note": "استملاك حكومي لمناطق واسعة شمال غرب المملكة"
  },
  {
    "name": "مسار قطار الحرمين الجديد",
    "type": "infrastructure",
    "cities": ["مكة المكرمة", "جدة", "المدينة المنورة"],
    "risk_level": "HIGH",
    "note": "امتدادات مخططة للقطار"
  }
]
```

**في `pipeline/red_flags.py`، أضف check:**
```python
import json

def _check_expropriation_risk(city: str, district: str) -> dict | None:
    try:
        with open("data/expropriation_zones.json", "r", encoding="utf-8") as f:
            zones = json.load(f)
        for zone in zones:
            if city in zone.get("cities", []):
                return {
                    "flag": "EXPROPRIATION_ZONE_RISK",
                    "severity": zone["risk_level"],
                    "message": f"المدينة ضمن نطاق: {zone['name']} — {zone['note']}"
                }
    except Exception:
        pass
    return None
```

**في `detect_red_flags()`:**
```python
exp_risk = _check_expropriation_risk(city, district)
if exp_risk:
    flags.append(exp_risk)
```

**بعد الاختبار:** `git commit -m "feat: expropriation zone risk detection"`

---

### الخطوة 3.2 — Absorption Rate Tracking

**المشكلة:** النظام يفترض بيع كل الوحدات — لكن لا يعرف هل السوق يستوعب ذلك.

**الحل — تتبع عمر الإعلانات:**

في `core/database.py`، أضف:
```sql
ALTER TABLE opportunities ADD COLUMN first_seen_at TEXT;
ALTER TABLE opportunities ADD COLUMN last_seen_at  TEXT;
ALTER TABLE opportunities ADD COLUMN days_on_market INTEGER;
```

**في `base.py` — عند السكريبينج:**
```python
# إذا كان الـ listing موجود → حدث last_seen_at
# إذا كان جديد → اضبط first_seen_at = now

# بعد 30 يوم من last_seen_at، الإعلان "اختفى" = بُيع على الأرجح
```

**في `pipeline/market_depth.py`، أضف:**
```python
def get_absorption_rate(city: str, district: str) -> dict:
    """
    حساب معدل امتصاص السوق:
    - كم إعلان ظهر الشهر الماضي؟
    - كم منهم اختفى (= بُيع)؟
    - معدل الامتصاص = (المباعة / الكلية) × 100
    """
    conn = get_connection()
    # ... حساب الأرقام
    return {
        "listed_last_30d":    listed,
        "sold_last_30d":      sold,
        "absorption_pct":     round(sold/listed*100) if listed else 0,
        "avg_days_on_market": avg_days,
    }
```

**في `analyzer.py`:**
```python
absorption = get_absorption_rate(city, district)
if absorption["absorption_pct"] < 20:
    score -= 2.0  # سوق راكد — معظم الوحدات لا تُباع
    market_ctx += f"\n⚠️ معدل امتصاص السوق ضعيف: {absorption['absorption_pct']}%"
```

**بعد الاختبار:** `git commit -m "feat: absorption rate tracking for market demand validation"`

---

## PHASE 4 — ربط CFO Dashboard بالواجهة

> **الهدف:** كل ما بُني في cfo_manager.py يظهر للمستخدم.

---

### الخطوة 4.1 — إضافة تبويب CFO في Dashboard

**الملف:** `dashboard/app.py`

**أضف Tab رابع "📈 تحليل CFO":**

```python
tab4_content:
  st.header("📈 تحليل المدير المالي (CFO View)")
  
  # اختيار الفرصة
  selected = st.selectbox("اختر الفرصة", opportunities_list)
  
  if selected:
      cfo = run_cfo_analysis(selected)
      
      col1, col2, col3 = st.columns(3)
      col1.metric("IRR السنوي", f"{cfo['irr_annual_pct']:.1f}%")
      col2.metric("رأس المال المطلوب", f"{cfo['equity_needed']:,.0f} ر.س")
      col3.metric("مدة الاسترداد", f"{cfo['payback_months']} شهر")
      
      # مقارنة البيع vs الإيجار vs Wafi
      st.subheader("مقارنة استراتيجيات الخروج")
      comparison_df = pd.DataFrame([
          {"الاستراتيجية": "بيع جاهز",       "IRR%": cfo['irr_sell'],   "رأس مال": cfo['equity_sell']},
          {"الاستراتيجية": "إيجار (10 سنوات)", "IRR%": cfo['irr_rent'],   "رأس مال": cfo['equity_rent']},
          {"الاستراتيجية": "بيع على الخارطة (وافي)", "IRR%": cfo['irr_wafi'], "رأس مال": cfo['equity_wafi']},
      ])
      st.dataframe(comparison_df)
      
      # Cashflow chart
      st.subheader("جدول التدفق النقدي")
      st.line_chart(pd.DataFrame(cfo['cashflow_monthly'], columns=['الشهر','التدفق']))
      
      # Sensitivity Matrix
      st.subheader("مصفوفة الحساسية")
      st.write("تأثير تغيير التكاليف وأسعار البيع على الربح")
      # ... رسم heatmap بـ plotly
```

**بعد الاختبار:** `git commit -m "feat: CFO dashboard tab with IRR, cashflow, exit strategy comparison"`

---

### الخطوة 4.2 — خريطة تفاعلية للفرص

**المكتبة:** `streamlit-folium` (أضفها لـ `requirements.txt`)

**في Dashboard، Tab جديد "🗺️ الخريطة":**

```python
import folium
from streamlit_folium import st_folium

def render_map_tab():
    m = folium.Map(location=[24.7, 46.7], zoom_start=6)  # الرياض كمركز
    
    for opp in opportunities:
        lat = opp.get("lat")
        lng = opp.get("lng")
        if not lat or not lng:
            continue
        
        score = opp.get("opportunity_score", 0)
        color = "green" if score >= 8 else "orange" if score >= 6 else "red"
        
        # نقطة على الخريطة
        folium.CircleMarker(
            location=[lat, lng],
            radius=8,
            color=color,
            popup=f"{opp['city']} | {opp['area_sqm']}م² | {opp['price_sar']:,} ر.س | Score: {score}",
        ).add_to(m)
        
        # مناطق الاستملاك كطبقة حمراء شفافة
        for zone in expropriation_zones:
            folium.Circle(
                location=zone["center"],
                radius=zone["radius_m"],
                color="red",
                fill=True,
                fill_opacity=0.1,
                tooltip=zone["name"],
            ).add_to(m)
    
    st_folium(m, width=900, height=600)
```

**بعد الاختبار:** `git commit -m "feat: interactive map with opportunity pins and risk zones"`

---

## PHASE 5 — تحسين جودة الـ AI

> **الهدف:** Ollama يضيف قيمة حقيقية وليس مجرد decoration.

---

### الخطوة 5.1 — حقن سياق السوق الكامل في Prompt

**الملف:** `pipeline/analyzer.py`

**بدل prompt بسيط، حقن:**
```python
def _build_enriched_prompt(listing_data: dict) -> str:
    city      = listing_data.get("city", "")
    district  = listing_data.get("district", "")
    price_sar = float(listing_data.get("price_sar") or 0)
    area_sqm  = float(listing_data.get("area_sqm") or 0)
    price_sqm = price_sar / area_sqm if area_sqm > 0 else 0
    
    bench      = get_benchmark(city, district) or get_benchmark(city, "")
    depth      = get_market_depth(city, district)
    absorption = get_absorption_rate(city, district)
    amenities  = listing_data.get("amenities_cache", {})
    trend      = get_price_trend(city, district)
    
    market_section = ""
    if bench:
        ratio = price_sqm / bench["avg"] if price_sqm else 0
        pct   = abs(1 - ratio) * 100
        direction = "أرخص" if ratio < 1 else "أغلى"
        market_section = f"""
=== بيانات السوق الموضوعية ===
متوسط سعر م² في {city} - {district}: {bench['avg']:,.0f} ريال (عينة: {bench['count']} صفقة)
هذا العقار {direction} من المتوسط بـ {pct:.1f}%
اتجاه السوق آخر 6 أشهر: {trend.get('direction','غير محدد')} ({trend.get('change_pct',0):+.1f}%)
عدد العروض النشطة في المنطقة: {depth.get('total_supply',0)} عقار
معدل الامتصاص الشهري: {absorption.get('absorption_pct',0)}%
متوسط مدة بقاء الإعلان: {absorption.get('avg_days_on_market',0)} يوم
المرافق في دائرة 2 كم: مدارس={amenities.get('schools',0)}, مستشفيات={amenities.get('hospitals',0)}, مساجد={amenities.get('mosques',0)}, محلات={amenities.get('shops',0)}
================================
"""
    
    return f"""أنت محلل عقاري خبير في سوق الأراضي السعودية. حلل الفرصة التالية بدقة:

{market_section}

=== تفاصيل العقار ===
المدينة: {city}
الحي: {district}
المساحة: {area_sqm} م²
السعر المطلوب: {price_sar:,.0f} ريال
سعر المتر: {price_sqm:,.0f} ريال
وصف الإعلان: {listing_data.get('title','')}

قدم تحليلاً يتضمن:
1. درجة الفرصة من 10 مع المبرر
2. نوع التطوير المناسب
3. مخاطر السوق في هذا الحي حالياً
4. التوصية النهائية (ابحث/تجاهل/انتظر)

أجب بـ JSON فقط."""
```

**بعد الاختبار:** `git commit -m "feat: enriched Ollama prompt with full market context injection"`

---

### الخطوة 5.2 — Confidence calibration حقيقي

**الملف:** `pipeline/analyzer.py`

```python
def _calculate_confidence(bench, ollama_succeeded: bool, depth) -> str:
    score = 0
    
    # جودة البنشمارك
    if bench and bench.get("source") == "reference":
        score += 3  # MOJ أو مصدر مستقل
    elif bench and bench.get("count", 0) >= 10:
        score += 2
    elif bench and bench.get("count", 0) >= 3:
        score += 1
    
    # Ollama
    if ollama_succeeded:
        score += 2
    
    # عمق السوق
    if depth and depth.get("total_supply", 0) >= 10:
        score += 1
    
    if score >= 5:   return "HIGH"
    elif score >= 3: return "MEDIUM"
    else:            return "LOW"
```

**بعد الاختبار:** `git commit -m "fix: confidence calibration uses benchmark source quality"`

---

## PHASE 6 — التحقق والاختبار الشامل

> **الهدف:** التأكد من أن كل الإصلاحات تعمل معاً.

---

### الخطوة 6.1 — اختبار End-to-End

```bash
# 1. تأكد أن الـ DB migrations نجحت
python -c "
import sys; sys.path.insert(0,'.')
from core.database import init_db
init_db()
print('DB migration OK')
"

# 2. جرب scraping من كل مصدر
python main.py --mode scrape

# 3. تحقق من النتائج في DB
python -c "
import sys; sys.path.insert(0,'.')
from core.database import get_connection
with get_connection() as conn:
    total   = conn.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0]
    priced  = conn.execute('SELECT COUNT(*) FROM opportunities WHERE price_sar > 0').fetchone()[0]
    dupes   = conn.execute('SELECT COUNT(*) FROM opportunities WHERE duplicate_of IS NOT NULL').fetchone()[0]
    benches = conn.execute('SELECT COUNT(*) FROM price_benchmarks').fetchone()[0]
    print(f'Total: {total} | With price: {priced} | Duplicates tagged: {dupes} | Benchmarks: {benches}')
"

# 4. تحقق من benchmark source
python -c "
import sys; sys.path.insert(0,'.')
from pipeline.benchmarks import get_benchmark
b = get_benchmark('الرياض', 'الياسمين')
print('Benchmark:', b)
print('Source:', b.get('source') if b else 'None — no data yet')
"
```

### الخطوة 6.2 — اختبار دقة التقييم المالي

```bash
python -c "
import sys; sys.path.insert(0,'.')
from pipeline.financial import calculate_roi_scenarios
from pipeline.market_rates import get_construction_cost, get_sibor_rate

# أرض تجريبية
test_listing = {
    'price_sar': 2_000_000,
    'area_sqm':  800,
    'city':      'الرياض',
    'district':  'الياسمين',
    'recommended_development': 'apartments'
}
cost = get_construction_cost('apartments')
rate = get_sibor_rate()
print(f'Construction cost: {cost} SAR/m² | SIBOR: {rate*100:.1f}%')
roi = calculate_roi_scenarios(test_listing)
for s in ['optimistic','expected','pessimistic']:
    print(f\"{s}: ROI {roi[s]['roi_pct']:.1f}% | Profit {roi[s]['gross_profit_sar']:,.0f}\")
"
```

### الخطوة 6.3 — Final commit

```bash
git add -A
git commit -m "feat: complete reliability overhaul — real benchmarks, dynamic costs, CFO dashboard, risk protection"
git push origin master
```

---

## 📋 متابعة التقدم

أضف هذا إلى `PROGRESS.md` وحدّثه بعد كل خطوة:

```markdown
## Critical Fixes Roadmap — Progress

### Phase 1 — Data Quality
- [ ] 1.1 Haraj price extraction from bodyTEXT
- [ ] 1.2 MOJ scraper verification and activation  
- [ ] 1.3 Separate benchmark from scraping data (reference_prices table)
- [ ] 1.4 Cross-platform deduplication (dedup.py)

### Phase 2 — Financial Accuracy
- [ ] 2.1 Dynamic construction cost via market_rates.py
- [ ] 2.2 Scoring uses independent benchmark source
- [ ] 2.3 Rental scenario (Build & Hold)

### Phase 3 — Risk Protection
- [ ] 3.1 Expropriation zones database (populated with real data)
- [ ] 3.2 Absorption rate tracking

### Phase 4 — Dashboard & UX
- [ ] 4.1 CFO tab with IRR, cashflow, exit strategy comparison
- [ ] 4.2 Interactive map with risk zones

### Phase 5 — AI Quality
- [ ] 5.1 Enriched Ollama prompt with full market context
- [ ] 5.2 Confidence calibration by benchmark source quality

### Phase 6 — Verification
- [ ] 6.1 End-to-end test
- [ ] 6.2 Financial accuracy test
- [ ] 6.3 Final commit + push
```

---

## ⚡ الترتيب الموصى به للتنفيذ

```
الأسبوع 1:  1.1 (Haraj price) + 1.4 (dedup)         — تأثير فوري على جودة البيانات
الأسبوع 2:  1.2 (MOJ verify) + 1.3 (ref benchmark)  — فصل البنشمارك عن نفسه
الأسبوع 3:  2.1 (market_rates) + 2.2 (scoring fix)  — تحليل مالي حقيقي
الأسبوع 4:  3.1 (expropriation) + 3.2 (absorption)  — حماية من الكوارث
الأسبوع 5:  4.1 (CFO tab) + 4.2 (map)               — واجهة للمستثمر الحقيقي
الأسبوع 6:  5.1 + 5.2 + 6.x                         — AI جودة + اختبار شامل
```

---

*آخر تحديث: 2026-04-17 | المرجع: تقييم شامل للمشروع بعد مراجعة كل ملفات pipeline/ و sources/ و core/*
