"""
Smoke tests — verify imports and DB incremental functions.
Run: pytest tests/test_smoke.py -v
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    import core.database as db_mod
    from pathlib import Path
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "test.db")
    db_mod.init_db()


# ── Import tests ──────────────────────────────────────────────────────────────

def test_core_imports():
    import core.logger
    import core.scheduler
    import core.database


def test_pipeline_imports():
    import pipeline.classifier
    import pipeline.matcher
    import pipeline.analyzer
    import pipeline.financial
    import pipeline.mockup
    import pipeline.notifier
    import pipeline.proposal


def test_scraper_imports():
    import sources.haraj.scraper
    import sources.aqar.scraper
    import sources.bayut.scraper
    import sources.propertyfinder.scraper
    import sources.wasalt.scraper


# ── DB function tests ─────────────────────────────────────────────────────────

def _opp(lid="t_001", source="test"):
    return dict(
        listing_id=lid, source=source, title="test land",
        city="Riyadh", district="", area_sqm=400.0,
        price_sar=1_200_000.0, contact_phone=None,
        contact_name=None, image_urls="", source_url="https://x.com",
    )


def test_save_opportunity_new():
    from core.database import save_opportunity
    assert save_opportunity(_opp()) is True


def test_save_opportunity_duplicate():
    from core.database import save_opportunity
    o = _opp("dup_001")
    assert save_opportunity(o) is True
    assert save_opportunity(o) is False


def test_listing_exists():
    from core.database import save_opportunity, listing_exists
    save_opportunity(_opp("ex_001"))
    assert listing_exists("ex_001") is True
    assert listing_exists("no_such_id") is False


def test_cursor_roundtrip():
    from core.database import set_cursor, get_cursor
    set_cursor("haraj", "haraj_999", 42)
    c = get_cursor("haraj")
    assert c["last_listing_id"] == "haraj_999"
    assert c["last_count"] == 42


def test_source_stats():
    from core.database import save_opportunity, get_source_stats
    save_opportunity(_opp("s1", "aqar"))
    save_opportunity(_opp("s2", "bayut"))
    stats = {r["source"]: r["count"] for r in get_source_stats()}
    assert stats.get("aqar") == 1
    assert stats.get("bayut") == 1


# ── Incremental base.run() test ───────────────────────────────────────────────

def test_base_run_incremental():
    from sources.base import BaseSource

    uid = str(int(time.time()))

    class MockScraper(BaseSource):
        name = "mock"

        def fetch(self):
            return [{"id": uid + "_A"}, {"id": uid + "_B"}, {"id": uid + "_C"}]

        def normalize(self, r):
            return _opp(lid="mock_" + r["id"], source="mock")

    s = MockScraper()
    run1 = s.run()
    run2 = s.run()

    assert len(run1) == 3, f"Expected 3 new on first run, got {len(run1)}"
    assert len(run2) == 0, f"Expected 0 new on second run, got {len(run2)}"

    from core.database import get_cursor
    cur = get_cursor("mock")
    assert cur["last_count"] == 3
