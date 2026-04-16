"""
Base class for all data sources.

run() implements probe-first logic:
  1. Fetch all raw items from the source
  2. Probe first 30 — if ALL are already known, the platform hasn't changed → skip
  3. Otherwise normalize & save only the NEW ones
"""
from abc import ABC, abstractmethod

from core.logger import get_logger

_PROBE_SIZE = 30

logger = get_logger("base")


class BaseSource(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Fetch raw listings from the source."""
        pass

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        """Normalize a raw listing to our schema."""
        pass

    def run(self) -> list[dict]:
        """
        Fetch → probe → save.
        Returns only NEW listings saved this run.
        """
        from core.database import listing_exists, save_opportunity, set_cursor

        raw_items = self.fetch()
        if not raw_items:
            return []

        # --- Probe: check first _PROBE_SIZE items ---
        probe_batch = raw_items[:_PROBE_SIZE]
        known_count = 0
        for r in probe_batch:
            if not r:
                continue
            try:
                lid = self.normalize(r).get("listing_id", "")
            except Exception:
                continue
            if lid and listing_exists(lid):
                known_count += 1

        if known_count == len(probe_batch) and len(probe_batch) >= _PROBE_SIZE:
            logger.info(
                f"[{self.name}] probe: all {_PROBE_SIZE} known — platform unchanged, skipping full run"
            )
            return []

        # --- Full run: normalize & save new items ---
        new_listings = []
        for r in raw_items:
            if not r:
                continue
            try:
                normalized = self.normalize(r)
            except Exception:
                continue
            lid = normalized.get("listing_id", "")
            if not lid:
                continue
            if not listing_exists(lid):
                save_opportunity(normalized)
                new_listings.append(normalized)

        if new_listings:
            set_cursor(
                self.name,
                last_listing_id=new_listings[0]["listing_id"],
                count=len(new_listings),
            )

        return new_listings
