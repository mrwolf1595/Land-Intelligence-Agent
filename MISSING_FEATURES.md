# 🏗️ Land Intelligence Agent — الميزات الناقصة للمنصة المتكاملة

> **الهدف:** تحويل الـ Agent من أداة سكريبينج + تقييم سطحي → منصة ذكاء عقاري كاملة
> تحمي صاحب الشأن من الخسارة وتعطيه قرار مبني على بيانات حقيقية.

---

## 📊 الوضع الحالي — ايش عندنا الحين

| الميزة | الحالة | المشكلة |
|--------|--------|---------|
| سكريبينج 4 منصات | ✅ يشتغل | بدون تحقق من صحة البيانات |
| تحليل Ollama | ✅ يشتغل | الموديل ما يعرف السوق الحقيقي |
| تقييم 0-10 | ✅ مع benchmark | بدون تاريخ أسعار — snapshot فقط |
| حساب ROI | ✅ مع benchmark | بس سيناريو واحد متفائل |
| كشف التكرار | ✅ يشتغل | بس بالسعر والمساحة — بدون coordinates |
| إشعارات واتساب | ✅ يشتغل | بدون تنبيهات ذكية (مثلاً: "السعر نزل!") |
| Dashboard Streamlit | ✅ أساسي | بدون فلترة متقدمة أو خرائط |

---

## 🔴 المرحلة 4 — الحماية من الخسارة (CRITICAL)

> بدون هذي الميزات الوكيل ممكن يورط صاحب الشأن بأرض فيها مشاكل

### 4.1 🚫 نظام الأعلام الحمراء (Red Flags Engine)
**المشكلة:** الحين لو سعر أرض أرخص بـ 50% من السوق — النظام يعتبرها فرصة ذهبية!
بينما الحقيقة إنها غالباً فخ (أرض عليها نزاع / بدون صك / منطقة ممنوع البناء فيها).

**المطلوب:**
```
pipeline/red_flags.py

def detect_red_flags(listing: dict, bench: dict) → list[RedFlag]:
    flags = []

    # 1. سعر مشبوه — أقل من 50% من السوق = غالباً مشكلة
    if ratio < 0.50:
        flags.append(RedFlag("PRICE_TOO_LOW", severity="HIGH",
            msg="السعر أقل من نصف سعر السوق — تحقق من وجود نزاع أو مشاكل قانونية"))

    # 2. بدون صك مذكور في النص
    if "صك" not in body and "رقم القطعة" not in body:
        flags.append(RedFlag("NO_DEED_MENTIONED", severity="MEDIUM",
            msg="لم يُذكر رقم الصك — تأكد من وجود صك إلكتروني"))

    # 3. كلمات خطر: "عاجل" + "السعر قابل للتفاوض" + سعر منخفض = scam vibes
    # 4. بائع بدون رقم واضح
    # 5. أرض بدون موقع محدد (حي/مخطط)
    # 6. مساحة غير منطقية (< 50م² أو > 100,000م²)

    return flags
```

**التكامل:** إذا أي flag بمستوى HIGH → النظام يعرض ⚠️ تحذير واضح ولا يرسل WhatsApp تلقائي.

---

### 4.2 📉 تاريخ الأسعار (Price History Tracker)
**المشكلة:** النظام يعرف سعر اليوم بس — ما يعرف هل السوق طالع أو نازل.
ممكن يقول "فرصة 9/10" على أرض في منطقة أسعارها نازلة من 3 شهور.

**المطلوب:**
```
core/database.py → جدول جديد:
    price_history (city, district, avg_price_sqm, recorded_at)

pipeline/trend.py:
    def get_price_trend(city, district, months=6) → dict:
        """
        Returns:
          direction: "UP" | "DOWN" | "STABLE"
          change_pct: 15.2  (النسبة خلال الفترة)
          monthly_points: [3200, 3100, 3000, ...]  # للرسم البياني
        """
```

**الآلية:**
- كل ما يشتغل `rebuild_benchmarks()` → يحفظ snapshot في `price_history`
- بعد شهر يكون عندك 30 نقطة بيانات → تقدر تحسب الاتجاه
- **القاعدة المهمة:** لو السوق نازل > 10% في آخر 3 شهور → نقّص الـ score بـ 2 نقطة

---

### 4.3 💰 تحليل مالي متعدد السيناريوهات
**المشكلة:** `calculate_roi()` يحسب سيناريو واحد بس (المتفائل).
لو ارتفعت تكلفة البناء 20%؟ لو ما باع بسرعة وقعد سنتين زيادة؟

**المطلوب:**
```
pipeline/financial.py → calculate_roi_scenarios()

return {
    "optimistic": { roi: 45%, timeline: 18mo },     # كل شي تمام
    "expected":   { roi: 22%, timeline: 24mo },      # السيناريو الواقعي
    "pessimistic":{ roi: -8%, timeline: 36mo },      # أسوأ حالة
    "breakeven_price_sqm": 2800,                     # أقل سعر بيع يعوض التكاليف
}

# السيناريو المتشائم يحسب:
# - تكلفة بناء +20%
# - سعر بيع -15%
# - مدة +50%
# - تمويل بنكي 7% لو محتاج
```

**القاعدة:** لو السيناريو المتشائم يخسر (ROI < 0) → يظهر تحذير أحمر.

---

### 4.4 🏦 حساب تكلفة التمويل
**المشكلة:** ROI يحسب كأنك دافع كاش — الحقيقة أغلب الناس تتمول.

**المطلوب:**
```
pipeline/financing.py

def calculate_with_financing(total_investment, financing_pct=0.7, rate=0.07, years=5):
    """
    financing_pct: كم نسبة تمويل (70% مثلاً)
    rate: نسبة الربح البنكي السنوي
    years: فترة السداد
    """
    equity = total_investment * (1 - financing_pct)
    loan = total_investment * financing_pct
    total_interest = loan * rate * years
    total_cost_with_finance = total_investment + total_interest

    return {
        "equity_needed": equity,           # كم تحتاج كاش
        "monthly_payment": (loan + total_interest) / (years * 12),
        "total_finance_cost": total_interest,
        "effective_roi": ...,              # ROI بعد التمويل
    }
```

---

### 4.5 📋 تكاليف مخفية (Hidden Costs Calculator)
**المشكلة:** ROI ما تحسب: رسوم نقل الملكية، رسوم البلدية، ضريبة التصرفات العقارية (5%)، تكاليف التسويق

**المطلوب:**
```
pipeline/hidden_costs.py

TRANSFER_FEE_PCT = 0.05        # ضريبة التصرفات العقارية 5%
MUNICIPALITY_FEES = 15_000     # رسوم بلدية (تقريبي)
MARKETING_PCT = 0.03           # 3% تسويق
LEGAL_FEES = 5_000             # رسوم محاماة/توثيق
CONTINGENCY_PCT = 0.10         # 10% احتياطي طوارئ

def total_hidden_costs(land_price, build_cost):
    return {
        "transfer_tax": land_price * TRANSFER_FEE_PCT,
        "municipality": MUNICIPALITY_FEES,
        "marketing": (land_price + build_cost) * MARKETING_PCT,
        "legal": LEGAL_FEES,
        "contingency": build_cost * CONTINGENCY_PCT,
        "total": ...  # مجموع الكل
    }
```

**ملاحظة:** ضريبة التصرفات العقارية 5% وحدها على أرض بـ 2 مليون = 100 ألف ريال!
هذا مبلغ يفرق بالـ ROI وما كان محسوب.

---

## 🟡 المرحلة 5 — ذكاء السوق (Market Intelligence)

### 5.1 🗺️ تقييم الموقع الجغرافي (Location Scoring)
**المشكلة:** النظام يعرف "جدة" بس — ما يعرف هل الأرض جنب مطار؟ جنب مدرسة؟ في حي راقي؟

**المطلوب:**
```
pipeline/location_score.py

def score_location(lat, lng, city, district) → dict:
    # باستخدام OpenStreetMap / Nominatim (مجاني)
    nearby = {
        "schools": count_nearby(lat, lng, "school", radius_km=2),
        "hospitals": count_nearby(lat, lng, "hospital", radius_km=5),
        "malls": count_nearby(lat, lng, "mall", radius_km=3),
        "mosques": count_nearby(lat, lng, "mosque", radius_km=1),
        "main_roads": distance_to_nearest(lat, lng, "highway"),
    }

    # Score: 0-10 based on amenities density
    location_score = ...

    return {
        "score": location_score,
        "nearby_amenities": nearby,
        "walkability": "HIGH" | "MEDIUM" | "LOW",
        "investment_grade": "A" | "B" | "C" | "D",
    }
```

**مصادر الإحداثيات:**
- بعض المنصات تعطيك lat/lng (مثل Aqar, Wasalt)
- الباقي → Nominatim geocoding من اسم الحي

---

### 5.2 🏗️ متابعة مشاريع حكومية (Government Projects Tracker)
**المشكلة:** لو في مشروع مترو أو طريق جديد قريب من الأرض → القيمة ترتفع 30-50%.
النظام ما يعرف عن المشاريع الحكومية.

**المطلوب:**
```
data/gov_projects.json — ملف يدوي (يتحدث كل شهر):
[
    {
        "name": "مترو الرياض - الخط الأول",
        "city": "الرياض",
        "affected_districts": ["العليا", "السليمانية", "الملز"],
        "impact": "HIGH_POSITIVE",
        "completion_year": 2027,
        "price_impact_pct": 30
    },
    {
        "name": "مشروع البحر الأحمر",
        "city": "ينبع",
        "affected_districts": [],
        "impact": "HIGH_POSITIVE",
        "completion_year": 2030
    },
    ...
]

pipeline/gov_impact.py:
def check_gov_projects(city, district) → list[dict]:
    """يرجع المشاريع الحكومية القريبة وتأثيرها على السعر"""
```

---

### 5.3 📊 تحليل العرض والطلب (Supply/Demand Ratio)
**المشكلة:** لو في منطقة 500 أرض معروضة وما أحد يشتري → السوق مشبع.
النظام ما يقيس كثافة العرض.

**المطلوب:**
```
pipeline/market_depth.py

def analyze_market_depth(city, district) → dict:
    # كم إعلان نشط في نفس المنطقة الحين؟
    active_listings = count_active(city, district)
    # كم إعلان بيع تم في آخر 3 شهور (من تاريخ الأسعار)
    recent_sales = count_sold(city, district, months=3)

    absorption_rate = recent_sales / active_listings if active_listings else 0

    return {
        "active_supply": active_listings,
        "monthly_absorption": absorption_rate,
        "months_of_inventory": 1/absorption_rate if absorption_rate else 99,
        "market_condition": "SELLER" if absorption_rate > 0.3 else
                           "BALANCED" if absorption_rate > 0.15 else
                           "BUYER",  # سوق مشتري = صعب تبيع
    }
```

**القاعدة:** لو `months_of_inventory > 12` (يعني العرض يكفي سنة بدون أي إعلان جديد)
→ خصم 2 نقطة من الـ score لأن البيع بيكون صعب.

---

### 5.4 🔄 مقارنة بالمعاملات الفعلية (Comparable Sales / Comps)
**المشكلة:** الـ benchmark الحين يقارن بعروض معلنة — مو بأسعار بيع فعلية.
سعر المعروض ≠ سعر البيع الحقيقي (عادة أقل بـ 10-20%).

**المطلوب:**
```
pipeline/comps.py

def find_comparable_sales(listing, radius_km=3, months=6) → list[dict]:
    """
    ابحث عن أراضي مشابهة:
    - نفس المدينة/الحي
    - مساحة ± 30%
    - تم بيعها (اختفت من المنصات) خلال آخر 6 شهور
    """
    # طريقة الكشف: إعلان كان موجود → اختفى → يعتبر "مبيوع"
    # سعره الأخير = تقدير لسعر البيع الفعلي (ناقص 10% تفاوض)
```

**الذكاء:** كل ما تختفي listing من المنصة → سجّلها كـ "probable sale" مع آخر سعر معروض.

---

## 🟢 المرحلة 6 — تنظيمية وقانونية

### 6.1 ✅ التحقق من الصك (Deed Verification Assist)
**المشكلة:** ما نقدر نتحقق إلكترونياً (ما في API حكومي مفتوح)، لكن نقدر نساعد.

**المطلوب:**
```
pipeline/deed_check.py

def generate_deed_checklist(listing) → dict:
    """قائمة مراجعة الصك للوسيط"""
    return {
        "checklist": [
            "☐ تأكد من وجود صك إلكتروني على منصة إملائي",
            "☐ تحقق من مطابقة المساحة في الصك مع المعلن",
            "☐ تأكد من عدم وجود رهن على الأرض",
            "☐ تحقق من تصنيف الأرض (سكني/تجاري) في الاسترشادي",
            "☐ أفراغ إلكتروني عبر ناجز فقط — ترفض أي طريقة ثانية",
            "☐ تأكد من عدم وجود نزاع مسجل في محكمة التنفيذ",
        ],
        "red_flags_from_text": [...],  # أي عبارات مشبوهة في الإعلان
        "estimated_transfer_tax": land_price * 0.05,
    }
```

---

### 6.2 📐 قيود البناء والتنظيم (Zoning & Building Codes)
**المشكلة:** ROI يحسب FAR = 3.0 للشقق — لكن كثير أحياء الـ FAR الحقيقي = 1.5 أو 2.0.
يعني النظام يبالغ بالأرباح.

**المطلوب:**
```
data/zoning_rules.json:
{
    "الرياض": {
        "default_far": 2.5,
        "districts": {
            "النرجس": {"far": 2.0, "max_floors": 4, "setback_m": 5},
            "حطين": {"far": 3.0, "max_floors": 6, "setback_m": 3},
            ...
        }
    }
}

pipeline/zoning.py:
def get_zoning_rules(city, district) → dict:
    """يرجع FAR الحقيقي + الارتدادات + الأدوار المسموحة"""
```

**الأثر:** `calculate_roi()` يستخدم FAR الحقيقي بدل القيمة الافتراضية → نتائج أدق.

---

## 🔵 المرحلة 7 — تجربة المستخدم والتشغيل

### 7.1 🗺️ خريطة تفاعلية في الداشبورد
**المشكلة:** الداشبورد الحين قائمة نصية بس — ما تشوف فين الأراضي على الخريطة.

**المطلوب:**
```
dashboard/app.py → تاب جديد "🗺️ خريطة الفرص"

# باستخدام streamlit-folium أو pydeck
import folium
from streamlit_folium import st_folium

# كل فرصة = marker على الخريطة
# لون الـ marker حسب الـ score:
#   أخضر = score > 7
#   أصفر = score 4-7
#   أحمر = score < 4
```

---

### 7.2 📱 بوت تليجرام (خيار ثاني للواتساب)
**المشكلة:** واتساب يحتاج Node.js + جلسة + ممكن ينقطع.
تليجرام أسهل 100× (Bot API مجاني ورسمي).

**المطلوب:**
```
sources/telegram/bot.py

# python-telegram-bot library
# أوامر:
#   /start    → عرف نفسك
#   /latest   → آخر 5 فرص
#   /top      → أعلى 3 فرص (score > 7)
#   /watch جدة النسيم  → تنبيهني لو في فرصة بهالمنطقة
#   /status   → حالة الـ scrapers
#   /roi <listing_id> → حساب ROI مفصل

# Inline alerts: كل فرصة score > 7 → إرسال تلقائي
```

---

### 7.3 📑 تقرير أسبوعي تلقائي (Weekly Digest)
**المشكلة:** الوسيط مشغول — ما يفتح الداشبورد كل يوم.

**المطلوب:**
```
pipeline/weekly_report.py

def generate_weekly_digest() → str:
    """
    كل يوم أحد الساعة 8 صباحاً يرسل ملخص:

    📊 ملخص الأسبوع — 10-16 أبريل 2026
    ━━━━━━━━━━━━━━━━━━━━
    🔍 تم مسح: 847 إعلان جديد
    ⭐ فرص عالية (score > 7): 12 فرصة
    🏆 أفضل فرصة: أرض 600م² في النسيم — ROI 45%
    📈 اتجاه الأسعار:
       الرياض ↗️ +3.2%
       جدة ↘️ -1.1%
       الدمام ➡️ ثابت
    ⚠️ أراضي عليها علامات حمراء: 5
    """
```

---

### 7.4 🔔 تنبيهات ذكية (Smart Alerts)
**المشكلة:** الحين النظام يرسل كل فرصة score > 6.
المفروض يرسل بس لما يصير شي مهم فعلاً.

**المطلوب:**
```
pipeline/smart_alerts.py

ALERT_TYPES = {
    "PRICE_DROP":     "🔻 السعر نزل! أرض في {district} نزل سعرها {pct}%",
    "NEW_HOT_DEAL":   "🔥 فرصة حارة! أرض {area}م² في {district} أرخص من السوق بـ {pct}%",
    "MARKET_SHIFT":   "📊 تغير السوق! أسعار {city} {direction} بنسبة {pct}%",
    "LISTING_REMOVED":"⚡ إعلان اختفى — غالباً انباع: {title}",
    "WATCHLIST_MATCH": "👀 إعلان جديد في منطقة تتابعها: {district}",
}
```

---

### 7.5 📋 Watchlist — قائمة المتابعة
**المشكلة:** الوسيط يبي يتابع مناطق محددة أو أراضي محددة.

**المطلوب:**
```
core/database.py → جدول:
    watchlist (
        id, user_id, watch_type,  -- "city", "district", "listing"
        city, district, listing_id,
        notify_on,  -- "new_listing", "price_drop", "any"
        created_at
    )
```

---

## ⚪ المرحلة 8 — بنية تحتية وجودة

### 8.1 🧪 اختبارات تلقائية (Automated Tests)
**المشكلة:** ولا test موجود. أي تعديل ممكن يكسر شي وما تدري.

**المطلوب:**
```
tests/
    test_price_extraction.py     # كل أنماط الأسعار العربية
    test_dedup.py                # تكرار بنفس البيانات
    test_benchmarks.py           # حساب المتوسطات
    test_red_flags.py            # كشف العلامات الحمراء
    test_financial.py            # ROI + سيناريوهات
    test_scrapers.py             # mock responses لكل scraper
```

---

### 8.2 📊 مراقبة صحة النظام (Health Monitoring)
**المشكلة:** لو scraper توقف ما أحد يدري إلا لما يفتح الداشبورد.

**المطلوب:**
```
core/health.py

def check_system_health() → dict:
    return {
        "scrapers": {
            "haraj":  {"last_run": "...", "status": "OK|STALE|ERROR"},
            "aqar":   ...,
        },
        "ollama": {"reachable": True, "model_loaded": True},
        "db_size_mb": 45.2,
        "listings_today": 127,
        "alerts": ["⚠️ Wasalt ما اشتغل من 48 ساعة"]
    }
```

---

### 8.3 🔄 إعادة معالجة بالبيانات الجديدة
**المشكلة:** الأراضي القديمة (200+ listing) قُيّمت بدون benchmarks.
محتاج mode يعيد تحليلها بالبيانات الجديدة.

**المطلوب:**
```
main.py --mode reprocess-all

# يأخذ كل listing مع processed=1
# يعيد: analyze_land() → calculate_roi() → update
# بس ما يرسل WhatsApp (عشان ما يغرق الوسيط)
```

---

## 📐 ترتيب الأولويات — ايش أسوي أول؟

| الأولوية | الميزة | السبب | الجهد |
|----------|--------|-------|-------|
| 🔴 **1** | 4.1 Red Flags | **يحمي من الخسارة مباشرة** | يومين |
| 🔴 **2** | 4.3 سيناريوهات مالية | يعطي الصورة الحقيقية | يوم |
| 🔴 **3** | 4.5 تكاليف مخفية | 5% ضريبة وحدها تقلب الميزان | نص يوم |
| 🟡 **4** | 4.2 تاريخ الأسعار | يحتاج وقت لتجميع بيانات | يوم (+ 30 يوم بيانات) |
| 🟡 **5** | 6.2 قيود البناء | FAR الحقيقي يغير ROI جذرياً | يومين (بحث + داتا) |
| 🟡 **6** | 5.3 عرض/طلب | يكشف المناطق المشبعة | يوم |
| 🟡 **7** | 4.4 حساب تمويل | أغلب المستثمرين يتمولون | نص يوم |
| 🟢 **8** | 7.4 تنبيهات ذكية | بدل إغراق الوسيط | يوم |
| 🟢 **9** | 7.1 خريطة تفاعلية | تجربة مستخدم أفضل | يوم |
| 🟢 **10** | 8.1 اختبارات | ثبات النظام | يومين |
| 🟢 **11** | 7.2 بوت تليجرام | أسهل من واتساب | يوم |
| 🟢 **12** | 5.1 تقييم الموقع | يحتاج geocoding | يومين |
| ⚪ **13** | 5.2 مشاريع حكومية | بيانات يدوية | يوم |
| ⚪ **14** | 5.4 مقارنات بيع | يحتاج بيانات تاريخية | أسبوع |
| ⚪ **15** | 7.3 تقرير أسبوعي | Nice-to-have | نص يوم |
| ⚪ **16** | 6.1 قائمة مراجعة الصك | مساعدة بس | نص يوم |
| ⚪ **17** | 7.5 Watchlist | تخصيص | يوم |
| ⚪ **18** | 8.2 مراقبة صحة | تشغيلي | نص يوم |
| ⚪ **19** | 8.3 إعادة معالجة | صيانة | نص يوم |

---

## 💡 القاعدة الذهبية

> **لو النظام ما يقدر يحدد بثقة > 80% إن الصفقة مربحة بعد كل التكاليف الحقيقية
> (ضريبة + تمويل + طوارئ + السيناريو المتشائم) → لا يرسل "فرصة" للوسيط.**

الأفضل يفوتك فرصة حقيقية من إنك تورط صاحب الشأن بخسارة.

---

## 🎯 الخلاصة

المشروع فيه 19 ميزة ناقصة رئيسية.
**أخطر 3 تنقص الحين** (بدونها ممكن خسارة حقيقية):

1. **Red Flags** — ما في حماية من العروض المشبوهة
2. **سيناريوهات مالية** — ROI وحيد ومتفائل
3. **تكاليف مخفية** — 5% ضريبة + رسوم = مئات الآلاف ما محسوبة

ابدأ بهذول الثلاث وبعدين كمّل الباقي بالترتيب.
