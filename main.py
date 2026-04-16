"""
Main Orchestrator.
Starts background sub-processes and schedules pipelines.
"""
import argparse
import subprocess
import time

from core.database import (
    init_db, is_processed, mark_processed,
    update_opportunity_analysis, mark_match_notified,
)
from core.logger import get_logger
from core.scheduler import AgentScheduler
from pipeline.matcher import run_matching
from pipeline.notifier import notify_broker_match, notify_broker_opportunity
from pipeline.analyzer import analyze_land
from pipeline.mockup import generate_mockup
from pipeline.financial import calculate_roi
from pipeline.proposal import generate_proposal
from config import FEATURES, ENABLED_SOURCES, MIN_OPPORTUNITY_SCORE, validate_config

logger = get_logger("main")


def run_matching_cycle():
    """Match requests ↔ offers, notify broker."""
    if not FEATURES["auto_match"]:
        return
    logger.info("Running matching cycle...")
    matches = run_matching()
    logger.info(f"Found {len(matches)} new matches")
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
            scraper_obj = module.Scraper()
            listings = scraper_obj.run()
            logger.info(f"{source_name}: {len(listings)} new listings this run")

            for listing in listings:
                _process_land_opportunity(listing)

        except Exception as e:
            logger.error(f"Source {source_name} error: {e}", exc_info=True)

    from core.database import get_source_stats
    for s in get_source_stats():
        logger.info(
            f"  DB [{s['source']}]: {s['count']} total | "
            f"last: {(s['last_seen'] or '')[:16]}"
        )


def _process_land_opportunity(listing: dict):
    """Full pipeline for a scraped land: analyze → ROI → mockup → PDF → DB → notify."""
    lid = str(listing.get("listing_id", ""))
    if not lid or is_processed(lid):
        return

    try:
        analysis = analyze_land(listing)
        score = analysis.get("opportunity_score", 0)

        if score < MIN_OPPORTUNITY_SCORE:
            mark_processed(lid, f"low_score_{score}")
            logger.info(f"Low score ({score}) — skipped: {listing.get('title', lid)}")
            return

        financial = calculate_roi(analysis)
        mockup = generate_mockup(analysis) if FEATURES["ai_mockup"] else None
        pdf = generate_proposal(analysis, financial, mockup) if FEATURES["pdf_proposal"] else None

        # ── Persist results to DB so dashboard can display them ──────────────
        update_opportunity_analysis(lid, analysis, financial, pdf)

        notify_broker_opportunity(analysis, financial, pdf)
        logger.info(
            f"Opportunity processed: {listing.get('title', lid)} "
            f"— score {score} | ROI {financial.get('roi_pct', 0)}%"
        )

    except Exception as e:
        logger.error(f"Opportunity processing error for {lid}: {e}", exc_info=True)


def start_python_bridge():
    """Start the FastAPI WhatsApp relay (must be up before Node.js sends messages)."""
    logger.info("Starting Python WhatsApp bridge...")
    from config import PYTHON_BRIDGE_PORT
    return subprocess.Popen([
        "uvicorn", "sources.whatsapp.bridge:app",
        "--host", "0.0.0.0", "--port", str(PYTHON_BRIDGE_PORT), "--log-level", "warning"
    ])


def start_whatsapp_node():
    """Start Node.js WhatsApp Web client."""
    logger.info("Starting WhatsApp Node.js client...")
    return subprocess.Popen(["node", "sources/whatsapp/client.js"])


def _wait_for_bridge(port: int, max_wait: int = 15) -> bool:
    """Poll the bridge /health endpoint until it responds or timeout."""
    import httpx
    url = f"http://localhost:{port}/health"
    for _ in range(max_wait):
        try:
            r = httpx.get(url, timeout=1)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["monitor", "scrape", "match", "all"], default="all")
    args = parser.parse_args()

    init_db()
    validate_config()
    logger.info(f"Land Intelligence Agent — Mode: {args.mode}")

    # ── WhatsApp: bridge FIRST, then Node.js client ───────────────────────────
    if args.mode in ("monitor", "all") and FEATURES["whatsapp_monitor"]:
        from config import PYTHON_BRIDGE_PORT
        start_python_bridge()
        ready = _wait_for_bridge(PYTHON_BRIDGE_PORT, max_wait=15)
        if ready:
            logger.info("Python bridge ready — starting WhatsApp Node.js client")
        else:
            logger.warning("Python bridge did not respond in time — starting Node.js anyway")
        start_whatsapp_node()
        time.sleep(2)

    # ── One-shot modes ────────────────────────────────────────────────────────
    if args.mode == "match":
        run_matching_cycle()
        return

    if args.mode == "scrape":
        run_scraping_cycle()
        return

    # ── Scheduled mode (all / monitor) ───────────────────────────────────────
    # Run an initial scrape shortly after startup so the user sees results fast.
    if args.mode in ("scrape", "all") and FEATURES["platform_scraping"]:
        logger.info("Scheduling initial scrape in 15 seconds...")
        import threading
        def _delayed_scrape():
            time.sleep(15)
            logger.info("Running startup scrape...")
            run_scraping_cycle()
        threading.Thread(target=_delayed_scrape, daemon=True).start()

    # Matching: 10-minute interval avoids "max instances reached" with slow Ollama
    # Scraping: hourly as planned
    scheduler = AgentScheduler(blocking=True)
    scheduler.add_interval(run_matching_cycle, minutes=10)
    scheduler.add_interval(run_scraping_cycle, hours=1)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.stop()
        logger.info("Agent stopped.")


if __name__ == "__main__":
    main()
