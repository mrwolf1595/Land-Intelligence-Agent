# 📈 سجل التقدم (Progress Log)

هذا الملف يوثق ما تم إنجازه من الميزات الناقصة المذكورة في `MISSING_FEATURES.md`. مخصص لمتابعة العمل بين مختلف وكلاء الذكاء الاصطناعي (AI Agents) الذين سيكملون التطوير.

---

## ✅ ما تم إنجازه حتى الآن

**المراحل السابقة (1, 2, 3):**
- استخراج الأسعار وتنظيف بيانات الحراج.
- اكتشاف التكرار الذكي وحساب المرجعية (Benchmarks).
- حقن سياق الأسعار في مهام Ollama.

**المرحلة 4: الحماية من الخسارة 🔴 (CRITICAL)**
- نظام الأعلام الحمراء (Red Flags Engine) يمنع الصفقات المشبوهة.
- السيناريوهات المالية 📊 (متفائل/متوقع/متشائم) شاملة التكاليف المخفية وتكاليف التمويل.
- تاريخ الأسعار لاكتشاف هبوط السوق خصم النقاط.

**المرحلة 5: ذكاء السوق 🟡 (Market Intelligence) — مُكتملة تقريباً ⏳**
1. **تحليل العرض والطلب (Market Depth):** إطلاق `pipeline/market_depth.py` لقياس التشبع والمخاطرة.
2. **قيود البناء والتنظيم (Zoning):** تطبيق أسس `data/zoning_rules.json` و `pipeline/zoning.py`.
3. **التنبيهات الذكية (Smart Alerts):** التوقف عن الإرسال المزعج (Spam) للوسيط.
4. **المؤشرات الموثوقة (Gov Data):** كتابة ذكية لـ `sources/moj/scraper.py` يستخدم الـ API السري لوزارة العدل لتخزين أسعار الصفقات الفعلية المفرغة كمعيار (Benchmark).
5. **تقييم الموقع (Location Scoring):** تنفيذ `sources/osm/scraper.py` باستخدام مكالمات Overpass لرفع تقييم الأرض إذا وجد مدارس، مستشفيات، أو مساجد ومحلات حولها في نطاق 2كم.

---

## 🟢 الخطوات القادمة (لـ AI المطور القادم)

يرجى الانتقال لإكمال المتبقي:

1. **الداشبورد المالي (CFO View في Streamlit):**
   - دمج حسابات الـ IRR و التدفقات النقدية (Cashflows) و الـ WAFI في الداشبورد برسم بياني.
2. **5.2 مشاريع حكومية (Government Projects):**
   - إنشاء قاعدة بيانات للمشاريع الكبيرة (تتبع).
3. **7.1 خريطة تفاعلية في الداشبورد:**
   - استخدام `streamlit-folium` لعرض الأراضي على الخريطة لتسهيل التصفح البصري للوسيط.
4. **8.1 اختبارات تلقائية (Automated Tests):**
   - إضافة نصوص اختبارات لمسارات `pipeline` الأساسية مثل استخراج الأسعار واكتشاف العلامات الحمراء لضمان الثبات.

**مكان الوقوف الحالي:** جميع الميزات المالية الأساسية والفلترة الذكية جاهزة وتعمل بثبات. المنصة الآن تعتبر ناضجة استثمارياً ولا تعطي قرارات طائشة.

---

## 🔴 خارطة الإصلاح الشامل (2026-04-17) — الأولوية القصوى

بعد مراجعة شاملة للمشروع، تم اكتشاف أن المشكلة الجوهرية هي **الفراغ البياني** — المعادلات صحيحة لكن الأرقام المرجعية وهمية أو مبنية على نفس البيانات المسكريبة.

**للتفاصيل الكاملة والكود وخطوات التنفيذ:** راجع `docs/CRITICAL_FIXES_ROADMAP.md`

### Critical Fixes — Progress Tracker

**Phase 1 — Data Quality (ابدأ هنا)**
- [ ] 1.1 Haraj price extraction from bodyTEXT (`sources/haraj/scraper.py`)
- [ ] 1.2 MOJ scraper verification and activation (`sources/moj/scraper.py`)
- [ ] 1.3 Separate benchmark from scraping data — add `market_reference_prices` table
- [ ] 1.4 Cross-platform deduplication — `core/dedup.py`

**Phase 2 — Financial Accuracy**
- [ ] 2.1 Dynamic construction cost + SIBOR — `pipeline/market_rates.py` (ملف جديد)
- [ ] 2.2 Scoring uses independent benchmark source quality
- [ ] 2.3 Rental scenario (Build & Hold) in `pipeline/financial.py`

**Phase 3 — Risk Protection**
- [ ] 3.1 Expropriation zones DB populated with Vision 2030 real data
- [ ] 3.2 Absorption rate tracking in `pipeline/market_depth.py`

**Phase 4 — Dashboard**
- [ ] 4.1 CFO tab in `dashboard/app.py` (IRR, cashflow, exit strategy)
- [ ] 4.2 Interactive map with `streamlit-folium` + risk zones overlay

**Phase 5 — AI Quality**
- [ ] 5.1 Enriched Ollama prompt with full market context injection
- [ ] 5.2 Confidence calibration by benchmark source quality

**Phase 6 — Verification**
- [ ] 6.1 End-to-end integration test
- [ ] 6.2 Financial accuracy spot-check
- [ ] 6.3 Final commit + push
