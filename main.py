"""
Main Orchestrator.
Starts background sub-processes and schedules pipelines.
"""
import argparse
import subprocess
import time

from core.database import init_db, is_processed, mark_processed
from core.logger import get_logger
from core.scheduler import AgentScheduler
from pipeline.matcher import run_matching
from pipeline.notifier import notify_broker_match, notify_broker_opportunity
from pipeline.analyzer import analyze_land
from pipeline.mockup import generate_mockup
from pipeline.financial import calculate_roi
from pipeline.proposal import generate_proposal
from core.database import mark_match_notified
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
            logger.error(f"Source {source_name} error: {e}")

    from core.database import get_source_stats
    for s in get_source_stats():
        logger.info(
            f"  DB [{s['source']}]: {s['count']} total | "
            f"last: {(s['last_seen'] or '')[:16]}"
        )


def _process_land_opportunity(listing: dict):
    """Full pipeline for a scraped land."""
    lid = str(listing.get("listing_id", ""))
    if not lid or is_processed(lid):
        return

    try:
        analysis = analyze_land(listing)
        score = analysis.get("opportunity_score", 0)

        if score < MIN_OPPORTUNITY_SCORE:
            mark_processed(lid, f"low_score_{score}")
            return

        financial = calculate_roi(analysis)
        mockup = generate_mockup(analysis) if FEATURES["ai_mockup"] else None
        pdf = generate_proposal(analysis, financial, mockup) if FEATURES["pdf_proposal"] else None

        notify_broker_opportunity(analysis, financial, pdf)
        mark_processed(lid, "done")
        logger.info(f"Opportunity processed: {listing.get('title', lid)} — score {score}")

    except Exception as e:
        logger.error(f"Opportunity processing error for {lid}: {e}")


def start_whatsapp_node():
    logger.info("Starting WhatsApp Node.js client...")
    return subprocess.Popen(["node", "sources/whatsapp/client.js"])


def start_python_bridge():
    logger.info("Starting Python WhatsApp bridge...")
    from config import PYTHON_BRIDGE_PORT
    return subprocess.Popen([
        "uvicorn", "sources.whatsapp.bridge:app",
        "--host", "0.0.0.0", "--port", str(PYTHON_BRIDGE_PORT), "--log-level", "warning"
    ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["monitor", "scrape", "match", "all"], default="all")
    args = parser.parse_args()

    init_db()
    validate_config()
    logger.info(f"Land Intelligence Agent — Mode: {args.mode}")

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

    scheduler = AgentScheduler(blocking=True)
    scheduler.add_interval(run_matching_cycle, minutes=2)
    scheduler.add_interval(run_scraping_cycle, hours=1)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        scheduler.stop()
        logger.info("Agent stopped.")


if __name__ == "__main__":
    main()
