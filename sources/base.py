"""
Base class for all data sources.
For Aqar and Wasalt, it connects to existing SQLite databases.
"""
from abc import ABC, abstractmethod

class BaseSource(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Fetch raw listings."""
        pass

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        """Normalize specific fields to our schema."""
        pass

    def run(self) -> list[dict]:
        """Fetch, normalize, deduplicate against DB. Returns only NEW listings."""
        from core.database import listing_exists, save_opportunity, set_cursor
        from datetime import datetime

        raw_items = self.fetch()
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
                count=len(new_listings)
            )
        return new_listings
