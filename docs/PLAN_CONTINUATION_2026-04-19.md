# Plan Continuation - 2026-04-19

## الهدف
إكمال خطة المشروع من نقطة Phase 1.3 (benchmark reliability) حتى إغلاق العوائق التقنية قبل SHIP.

## ما تم تنفيذه فعليًا

### 1) Benchmark reliability
- تحديث `pipeline/benchmarks.py` لإرجاع metadata إضافية:
  - `source`
  - `as_of`
- تفعيل شرط fallback للـ scraped benchmarks فقط عند:
  - `sample_count >= 5`
- إضافة freshness guard للمرجع المستقل:
  - رفض بيانات MOJ/local_moj القديمة (stale) بعد فترة صلاحية.

### 2) Analyzer propagation
- تحديث `pipeline/analyzer.py` لتمرير:
  - `benchmark_source`
  - `benchmark_as_of`

### 3) Broker-facing transparency
- تحديث `pipeline/notifier.py` لإظهار block مرجعية التسعير في رسالة WhatsApp:
  - المصدر
  - حجم العينة
  - آخر تحديث

### 4) Proposal transparency
- تحديث `pipeline/proposal.py` + `templates/proposal_template.html` لإظهار قسم Provenance داخل PDF.

### 5) Verification and contracts
- إضافة suite جديدة: `tests/test_phase1_3_benchmark_contracts.py`
  - precedence (moj > local_moj > scraped)
  - fallback threshold
  - provenance fields
  - stale reference fallback
  - notifier provenance mention
- إصلاح test stub قديم في `tests/test_phase1_phase2_contracts.py` ليتوافق مع response object الحالي.

## نتائج الاختبارات
- تم تشغيل 10 اختبارات عقود (Phase 1/2 + Phase 1.3)
- النتيجة: 10/10 PASS

## حالة Gate بعد إعادة التقييم
- Scope: APPROVED
- Design: APPROVED
- Verify: NO-SHIP
- Ship: HOLD

## المتبقي فقط قبل SHIP
1. تشغيل end-to-end parity فعلي (بيئة تشغيل حقيقية).
2. إثبات real-device لرسالة WhatsApp بعد آخر تعديل.
3. إثبات PDF فعلي يظهر provenance بشكل واضح.
4. إرفاق artifacts في Gate 4/5 ثم إعادة re-gate سريع.

## تقدير المرحلة التالية
هذه المرحلة تشغيلية أكثر من كونها برمجية؛ الزمن المتوقع قصير بعد توفر التحقق على الهاتف.
