"""
Broker dashboard Streamlit UI
Run: streamlit run dashboard/app.py
"""
import streamlit as st
import sqlite3
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.database import init_db

init_db()   # creates tables if they don't exist yet

st.set_page_config(page_title="Land Agent Dashboard", layout="wide", page_icon="🏗️")
st.title("🏗️ Land Intelligence Agent — Broker Dashboard")

DB = Path("db/agent.db")


def get_conn():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


tab1, tab2, tab3 = st.tabs(["🔗 تطابقات جديدة", "🏗️ فرص الأراضي", "📊 إحصائيات"])

with tab1:
    st.subheader("تطابقات الطلب والعرض — بانتظار قرارك")

    conn = get_conn()
    rows = conn.execute("""
        SELECT m.*,
               req.raw_text  AS req_text,
               req.sender_name  AS req_name,
               req.sender_phone AS req_phone,
               req.city         AS req_city,
               req.price_sar    AS req_price,
               off.raw_text     AS off_text,
               off.sender_name  AS off_name,
               off.sender_phone AS off_phone,
               off.city         AS off_city,
               off.price_sar    AS off_price
        FROM matches m
        JOIN messages req ON m.request_id = req.id
        JOIN messages off ON m.offer_id   = off.id
        WHERE m.broker_action = 'pending'
        ORDER BY m.match_score DESC
    """).fetchall()
    conn.close()

    matches = [dict(r) for r in rows]

    if not matches:
        st.info("لا يوجد تطابقات جديدة حالياً")
    else:
        st.write(f"**{len(matches)} تطابق** بانتظار المراجعة")
        for m in matches:
            score = m["match_score"]
            score_color = "🟢" if score >= 0.8 else "🟡" if score >= 0.65 else "🟠"
            with st.expander(f"{score_color} تطابق {int(score*100)}% — {m['req_name']} ↔ {m['off_name']}"):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**📋 الطالب**")
                    st.write(m["req_text"])
                    if m["req_price"]:
                        st.caption(f"المدينة: {m['req_city']} | السعر: {m['req_price']:,.0f} ر.س")
                    st.code(f"رقم الاتصال: {m['req_phone']}")
                with c2:
                    st.markdown("**🏗️ العارض**")
                    st.write(m["off_text"])
                    if m["off_price"]:
                        st.caption(f"المدينة: {m['off_city']} | السعر: {m['off_price']:,.0f} ر.س")
                    st.code(f"رقم الاتصال: {m['off_phone']}")

                st.info(f"💡 {m['match_reasoning']}")

                col_a, col_b, _ = st.columns(3)
                if col_a.button("✅ تواصلت", key=f"act_{m['id']}"):
                    conn2 = get_conn()
                    conn2.execute("UPDATE matches SET broker_action='contacted' WHERE id=?", (m["id"],))
                    conn2.commit()
                    conn2.close()
                    st.rerun()
                if col_b.button("❌ تجاهل", key=f"rej_{m['id']}"):
                    conn2 = get_conn()
                    conn2.execute("UPDATE matches SET broker_action='rejected' WHERE id=?", (m["id"],))
                    conn2.commit()
                    conn2.close()
                    st.rerun()

with tab2:
    st.subheader("فرص الأراضي المحللة")
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM opportunities WHERE processed=1 AND duplicate_of IS NULL ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    conn.close()

    opps = [dict(r) for r in rows]

    if not opps:
        st.info("لا يوجد فرص محللة بعد")
    else:
        for o in opps:
            analysis = json.loads(o["analysis"] or "{}") if o["analysis"] else {}
            fin = json.loads(o["financial"] or "{}") if o["financial"] else {}
            score = analysis.get("opportunity_score", 0)
            roi = fin.get("roi_pct", 0)
            confidence = o.get("confidence") or "LOW"
            conf_badge = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🔴"}.get(confidence, "🔴")

            # Red flags indicator
            red_flags = analysis.get("red_flags", [])
            high_flags = [f for f in red_flags if f.get("severity") == "HIGH"]
            flag_indicator = ""
            if high_flags:
                flag_indicator = f" ⛔ {len(high_flags)} تحذير خطير"
            elif red_flags:
                flag_indicator = f" ⚠️ {len(red_flags)} ملاحظة"

            with st.expander(f"📍 {o['title']} — Score: {score}/10 | ROI: {roi}% {conf_badge} {confidence}{flag_indicator}"):
                # ── Top metrics row ──────────────────────────────────────────
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("سعر الأرض", f"{o['price_sar']:,.0f} ر.س" if o["price_sar"] else "—")
                c2.metric("صافي الربح", f"{fin.get('gross_profit_sar', 0):,.0f} ر.س")
                c3.metric("ROI (مع التكاليف)", f"{roi}%")
                c4.metric("التكاليف المخفية", f"{fin.get('hidden_costs_sar', 0):,.0f} ر.س")

                # ── Red Flags section ────────────────────────────────────────
                if red_flags:
                    st.markdown("---")
                    st.markdown("**🚩 علامات تحذيرية:**")
                    for flag in red_flags:
                        severity = flag.get("severity", "LOW")
                        color = {"HIGH": "red", "MEDIUM": "orange", "LOW": "gray"}[severity]
                        st.markdown(f":{color}[{flag.get('message', '')}]")

                # ── Scenarios section ────────────────────────────────────────
                scenarios = fin.get("scenarios", {})
                if scenarios:
                    st.markdown("---")
                    st.markdown("**📊 سيناريوهات الاستثمار:**")
                    sc1, sc2, sc3 = st.columns(3)
                    opt = scenarios.get("optimistic", {})
                    exp = scenarios.get("expected", {})
                    pes = scenarios.get("pessimistic", {})

                    sc1.metric(
                        "🟢 متفائل",
                        f"ROI {opt.get('roi_pct', 0)}%",
                        f"ربح {opt.get('gross_profit_sar', 0):,.0f} ر.س",
                    )
                    sc2.metric(
                        "🟡 متوقع",
                        f"ROI {exp.get('roi_pct', 0)}%",
                        f"ربح {exp.get('gross_profit_sar', 0):,.0f} ر.س",
                    )
                    pes_profit = pes.get("gross_profit_sar", 0)
                    # Pass signed value so Streamlit renders red↓ for losses.
                    # Using abs() with an Arabic prefix fools Streamlit into showing
                    # a green↑ arrow even on a loss — so we pass the raw signed number.
                    sc3.metric(
                        "🔴 متشائم",
                        f"ROI {pes.get('roi_pct', 0)}%",
                        f"{pes_profit:,.0f} ر.س",
                        delta_color="normal",
                    )

                    if scenarios.get("pessimistic_loss"):
                        st.error("⛔ السيناريو المتشائم يُظهر خسارة — ادرس جيداً قبل الاقدام")

                    # Breakeven
                    be = scenarios.get("breakeven_sell_sqm", 0)
                    if be > 0:
                        st.caption(f"💰 سعر البيع الأدنى لعدم الخسارة: {be:,} ر.س/م²")

                    # Financing
                    financing = scenarios.get("financing", {})
                    if financing.get("loan_amount", 0) > 0:
                        st.markdown("---")
                        st.markdown("**🏦 لو تمويل بنكي 70%:**")
                        fc1, fc2, fc3 = st.columns(3)
                        fc1.metric("كاش مطلوب", f"{financing.get('equity_needed', 0):,.0f} ر.س")
                        fc2.metric("قسط شهري", f"{financing.get('monthly_payment', 0):,.0f} ر.س")
                        fc3.metric("ROI بعد التمويل", f"{financing.get('effective_roi_pct', 0)}%")

                # ── PDF download ─────────────────────────────────────────────
                if o.get("pdf_path") and os.path.exists(o["pdf_path"]):
                    with open(o["pdf_path"], "rb") as f:
                        st.download_button(
                            "⬇️ تحميل Proposal PDF",
                            f.read(),
                            file_name=os.path.basename(o["pdf_path"]),
                            mime="application/pdf",
                        )

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

    st.divider()
    st.subheader("📡 حالة Scrapers — آخر تشغيل")

    conn = get_conn()
    source_rows = conn.execute("""
        SELECT o.source,
               COUNT(*)          AS total,
               MAX(o.created_at) AS last_seen,
               c.last_run_at,
               c.last_count
        FROM opportunities o
        LEFT JOIN scraper_cursors c ON c.source = o.source
        GROUP BY o.source
        ORDER BY o.source
    """).fetchall()
    conn.close()

    if not source_rows:
        st.info("لم يتم تشغيل أي scraper بعد — شغّل: python main.py --mode scrape")
    else:
        scols = st.columns([2, 1, 2, 2, 1])
        scols[0].markdown("**المنصة**")
        scols[1].markdown("**الإعلانات**")
        scols[2].markdown("**آخر إعلان**")
        scols[3].markdown("**آخر تشغيل**")
        scols[4].markdown("**جديد (آخر run)**")
        for row in source_rows:
            r = dict(row)
            scols = st.columns([2, 1, 2, 2, 1])
            scols[0].write(r["source"])
            scols[1].write(r["total"])
            last_seen = (r["last_seen"] or "")[:16].replace("T", " ")
            scols[2].write(last_seen)
            last_run = (r["last_run_at"] or "لم يُشغَّل")[:16].replace("T", " ")
            scols[3].write(last_run)
            scols[4].write(r["last_count"] or 0)
