# Local Data Integration — civillizard/Saudi-Real-Estate-Data

## Overview

الريبو `civillizard/Saudi-Real-Estate-Data` مربوط مباشرةً بالمشروع ويوفر:

| المصدر | السجلات | الفائدة |
|--------|---------|---------|
| MOJ Sales (2020-2025) | 1.25M صفقة | بنشمارك أسعار لكل مدينة/حي في المملكة |
| REGA Rentals | 19,954 صف | معدلات إيجار حقيقية (13 منطقة) |
| KAPSARC Price Index | 276 قراءة | مؤشر أسعار ربعي 2021-2025 (أساس 2023=100) |
| GASTAT REPI | 6,509 صف | مؤشر أسعار عقارية إقليمي مع YoY/QoQ |

---

## الملف الرئيسي: `pipeline/local_data.py`

### دوال الاستيراد (تشغّل مرة واحدة/يوم)

```python
from pipeline.local_data import run_all_imports

# عند بدء المشروع (main.py)
run_all_imports()                # يتجاوز تلقائياً إذا نُفّذ اليوم
run_all_imports(force=True)      # يعيد الاستيراد (بعد git pull)
```

### دوال الاستعلام

```python
from pipeline.local_data import (
    get_rental_rate,           # SAR/سنة/وحدة
    get_rental_yield_pct,      # yield% تقريبي على أساس سعر الأرض
    get_national_price_trend,  # KAPSARC — حركة المؤشر الوطني
    get_repi_for_city,         # GASTAT — مؤشر المنطقة مع YoY%
)
```

---

## أولوية بنشمارك الأسعار (`pipeline/benchmarks.py`)

```
1. source='moj'       ← API مباشر (19 حي trending) — أحدث بيانات
2. source='local_moj' ← CSV محلي (7,586 مدينة/حي) — أشمل تغطية
3. price_benchmarks   ← أسعار طلب مكشوطة (fallback)
```

---

## سيناريو الإيجار في `calculate_roi_scenarios()`

أُضيف كـ `scenarios["rental"]`:

```python
{
  "strategy": "build_and_hold",
  "num_units": 13,
  "avg_unit_size_sqm": 110,
  "annual_rent_per_unit": 48000,       # SAR/سنة — من REGA أو market_estimate
  "gross_annual_income": 624000,
  "net_annual_income": 530400,         # بعد خصم 15% تشغيل وشواغر
  "annual_yield_pct": 7.02,
  "payback_years": 14.3,
  "rental_data_source": "rega"         # أو "market_estimate" للمدن الكبرى
}
```

---

## أسعار إيجار المدن الكبرى (Market Estimates)

REGA لا تغطي المدن الكبرى (الرياض/جدة/الدمام). القيم التالية مُدخلة كـ `source='market_estimate'` بناءً على تقارير السوق:

| المدينة | شقة/سنة | فيلا/سنة | محل/سنة |
|---------|---------|---------|---------|
| الرياض | 48,000 | 100,000 | 72,000 |
| جدة | 44,000 | 90,000 | 65,000 |
| مكة | 40,000 | 80,000 | 60,000 |
| المدينة المنورة | 32,000 | 65,000 | 48,000 |
| الدمام | 36,000 | 72,000 | 54,000 |
| الخبر | 40,000 | 78,000 | 58,000 |
| الأحساء | 24,000 | 50,000 | 36,000 |

لتحديث هذه القيم بأرقام حقيقية → استخدم Ejar API (موثّق في `docs/EJAR_API_ANALYSIS.md`).

---

## توحيد أسماء المدن

MOJ تستخدم تهجئة عامية (`جده`) بدل الفصيحة (`جدة`). الخريطة معرّفة في `_CITY_ALIASES` داخل `local_data.py` وتُطبَّق أثناء الاستيراد.

المدن المعالجة: جدة → `جده`, المدينة المنورة → `الالمنورة`, أبها → `ابها`, الأحساء → `الهفوف`, جازان → `جيزان`, وغيرها.

---

## الجداول الجديدة في SQLite

```sql
rental_benchmarks     — (city, district, property_type_ar) → avg_annual_rent_sar, yield
price_index_history   — (year, quarter, sector)            → KAPSARC quarterly index
repi_index            — (year, quarter, region, category)  → GASTAT regional index
data_import_log       — (source)                           → last import timestamp
```

---

## تحديث البيانات

```bash
# بعد git pull للريبو
cd "K:\Projects\Land Intelligence Agent"
python main.py --reimport   # يعيد استيراد كل المصادر
```

---

## ما زال ناقصاً

| الميزة | الحل المقترح |
|--------|-------------|
| إيجارات المدن الكبرى بدقة | ربط Ejar API (موثّق في `docs/EJAR_API_ANALYSIS.md`) |
| إيجار الأراضي التجارية | Ejar API — category = 'commercial_land' |
| SAMA معدل فائدة ديناميكي | `SAMA-Table-12e.csv` — يحتاج parser مخصص لملف البيانات |
| تكاليف البناء الديناميكية | `KAPSARC-Construction-Cost-Index.csv` — جاهز للربط |
| تريند أسعار الأحياء تاريخياً | MOJ quarterly splits — يمكن بناؤه من ملفات السنوات |
