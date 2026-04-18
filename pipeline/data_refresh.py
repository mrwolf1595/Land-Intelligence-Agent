"""
Weekly Data Refresh Pipeline
==============================
Runs automatically once per week to keep all market data fresh.

What gets updated:
  1. Ejar API      → rental_benchmarks (source='ejar') — real contract data
  2. MOJ API       → market_reference_prices (source='moj') — trending districts
  3. git pull repo → Saudi-Real-Estate-Data (MOJ CSV + KAPSARC + GASTAT)
  4. Re-import     → local_data.run_all_imports(force=True) after pull

Trigger: Called from AgentScheduler in main.py (every 7 days)
Manual:  python -m pipeline.data_refresh
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

from core.database import get_conn
from core.logger import get_logger

logger = get_logger("data_refresh")

_REPO = Path(__file__).parent.parent / "Saudi-Real-Estate-Data"


# ── 1. Ejar live rental data ──────────────────────────────────────────────────

def refresh_ejar() -> int:
    """Fetch live Ejar rental data for all Saudi cities. ~5-10 min."""
    logger.info("[refresh] Starting Ejar rental update...")
    try:
        from sources.ejar.scraper import update_rental_benchmarks
        n = update_rental_benchmarks()
        logger.info(f"[refresh] Ejar: {n} records updated")
        return n
    except Exception as e:
        logger.error(f"[refresh] Ejar failed: {e}", exc_info=True)
        return 0


# ── 2. MOJ API live trending districts ───────────────────────────────────────

def refresh_moj_api() -> int:
    """Pull latest MOJ trending districts (fast — ~19 districts)."""
    logger.info("[refresh] Starting MOJ API update...")
    try:
        from sources.moj.scraper import update_reference_prices
        from core.database import get_conn
        conn = get_conn()
        n = update_reference_prices(conn=conn)
        conn.close()
        logger.info(f"[refresh] MOJ API: {n} trending districts updated")
        return n
    except Exception as e:
        logger.error(f"[refresh] MOJ API failed: {e}", exc_info=True)
        return 0


# ── 3. git pull Saudi-Real-Estate-Data repo ───────────────────────────────────

def pull_data_repo() -> bool:
    """
    Run `git pull` on the Saudi-Real-Estate-Data repo.
    Returns True if pull succeeded (even if already up-to-date).
    """
    if not _REPO.exists():
        logger.warning(f"[refresh] Repo not found: {_REPO} — skipping git pull")
        return False

    logger.info(f"[refresh] Running git pull on {_REPO.name}...")
    try:
        result = subprocess.run(
            ["git", "-C", str(_REPO), "pull", "--ff-only"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            if "Already up to date" in stdout:
                logger.info("[refresh] Repo already up to date")
            else:
                logger.info(f"[refresh] Repo updated: {stdout[:200]}")
            return True
        else:
            logger.error(f"[refresh] git pull failed (code={result.returncode}): {stderr}")
            return False

    except subprocess.TimeoutExpired:
        logger.error("[refresh] git pull timed out after 120s")
        return False
    except FileNotFoundError:
        logger.error("[refresh] git not found in PATH — install git or skip repo pull")
        return False
    except Exception as e:
        logger.error(f"[refresh] git pull error: {e}")
        return False


# ── 4. Re-import after git pull ───────────────────────────────────────────────

def reimport_local_data() -> dict:
    """Re-run all local CSV imports (called after successful git pull)."""
    logger.info("[refresh] Re-importing local CSV data...")
    try:
        from pipeline.local_data import run_all_imports
        return run_all_imports(force=True)
    except Exception as e:
        logger.error(f"[refresh] Local data reimport failed: {e}", exc_info=True)
        return {}


# ── Main entry point ──────────────────────────────────────────────────────────

def run_weekly_refresh() -> dict:
    """
    Execute the full weekly data refresh cycle.

    Order matters:
      • Ejar first  — live data, independent of repo
      • MOJ API     — quick, always fresh
      • git pull    — then reimport if anything changed
      • reimport    — only if pull succeeded and returned new commits

    Returns: summary dict with counts per source.
    """
    start = datetime.now()
    logger.info("=" * 60)
    logger.info(f"[refresh] Weekly data refresh started — {start.strftime('%Y-%m-%d %H:%M')}")
    logger.info("=" * 60)

    results: dict = {}

    # 1. Ejar live rental
    results["ejar"] = refresh_ejar()

    # 2. MOJ API trending
    results["moj_api"] = refresh_moj_api()

    # 3. git pull repo
    pulled = pull_data_repo()

    # 4. Reimport if pull succeeded
    if pulled:
        local = reimport_local_data()
        results.update({f"local_{k}": v for k, v in local.items()})
    else:
        logger.info("[refresh] Skipping reimport (no git pull or already up to date)")

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(
        f"[refresh] Weekly refresh complete in {elapsed:.0f}s — "
        + " | ".join(f"{k}={v}" for k, v in results.items())
    )

    # Persist refresh timestamp
    try:
        conn = get_conn()
        conn.execute("""
            INSERT INTO data_import_log (source, imported_at, record_count)
            VALUES ('weekly_refresh', ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                imported_at  = excluded.imported_at,
                record_count = excluded.record_count
        """, (datetime.now().isoformat(), sum(v for v in results.values() if isinstance(v, int))))
        conn.commit()
        conn.close()
    except Exception:
        pass

    return results


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from core.database import init_db
    init_db()

    import argparse
    parser = argparse.ArgumentParser(description="Weekly market data refresh")
    parser.add_argument("--ejar-only",  action="store_true", help="Only update Ejar rental data")
    parser.add_argument("--moj-only",   action="store_true", help="Only update MOJ trending")
    parser.add_argument("--pull-only",  action="store_true", help="Only git pull + reimport")
    args = parser.parse_args()

    if args.ejar_only:
        refresh_ejar()
    elif args.moj_only:
        refresh_moj_api()
    elif args.pull_only:
        if pull_data_repo():
            reimport_local_data()
    else:
        run_weekly_refresh()
