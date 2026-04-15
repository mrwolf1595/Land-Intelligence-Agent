# Session Memory — 2026-04-15 (Session 3)

## What shipped

### Incremental Scraping System (priority work)
- **`core/database.py` — new functions**:
  - `save_opportunity(opp) -> bool` — INSERT OR IGNORE, returns True if new row
  - `listing_exists(listing_id) -> bool` — fast dedup check
  - `get_source_stats() -> list[dict]` — per-source count + last_seen
  - `get_cursor(source) -> dict` — reads last_run_at / last_listing_id / last_count
  - `set_cursor(source, last_listing_id, count)` — UPSERT after each run
  - Fixed `mark_processed()` — INSERT OR IGNORE before UPDATE (was silent no-op)
  - Added `scraper_cursors` table to `init_db()`

- **`sources/base.py` — incremental `run()`**:
  - Calls `listing_exists()` before saving → skips known listings
  - Calls `save_opportunity()` for new ones → persists to DB automatically
  - Calls `set_cursor()` at end of run
  - Returns **only NEW listings** (first run = all; subsequent = delta only)

- **`sources/wasalt/scraper.py` — complete rewrite**:
  - Primary: HTTP GET `https://wasalt.sa/sale/search?page=N`, extracts `__NEXT_DATA__` JSON
  - Filters by `propertySubType ∈ {أرض, أرض متعددة الاستخدام, أرض تجارية}`
  - Early-stop: quits after 15 consecutive known listing IDs
  - Falls back to SQLite adapter if HTTP returns 403
  - `normalize()` handles both web-scraper and SQLite paths

- **Bayut scraper — incremental enhancement**:
  - Reads `last_run_at` cursor → adds Algolia `numericFilters: updatedAt > <ts>`
  - Early-stop at 30 consecutive known hits
  
- **Aqar / Haraj / PropertyFinder scrapers — incremental early-stop**:
  - Each checks `listing_exists()` per listing
  - Stops after 10 consecutive known listings per page/city

- **`dashboard/app.py` — Scraper Status section**:
  - New section in Statistics tab: per-source table showing total listings,
    last listing seen, last run time, and new count from last run
  - Reads from `opportunities JOIN scraper_cursors`

## Architecture: Incremental Flow
```
scraper.run()
  │
  ├─ fetch()           ← platform-specific HTTP / API
  │    └─ early-stop when N consecutive known IDs hit
  │
  ├─ for each raw item:
  │    normalize() → listing_id
  │    listing_exists(listing_id)? → skip
  │    save_opportunity()          → INSERT OR IGNORE
  │    append to new_listings
  │
  └─ set_cursor(source, first_new_id, count)
     return new_listings  ← only deltas
```

## Tests run (all passed)
- `save_opportunity`: first insert True, duplicate False ✓
- `listing_exists`: True/False correctly ✓
- `get_cursor` / `set_cursor` roundtrip ✓
- `base.run()` mock: run1=3 new, run2=0 new ✓
- All 5 scraper imports: OK ✓

## Wasalt web scraping status
- Wasalt.sa: Next.js SSR with `__NEXT_DATA__` containing `searchResult.properties`
- URL pattern: `/sale/search?page=N` → 32 items/page, mixed types
- ~6% are land listings (`propertySubType=أرض`)
- Python httpx: **likely blocked (403)** → scraper falls back to SQLite adapter
- Browser: fully accessible, data confirmed in `__NEXT_DATA__`
- If Wasalt unblocks httpx (e.g., on a different IP/server): web scraper activates automatically

## Current state
| Component | Status |
|---|---|
| `core/database.py` | ✅ incremental functions added |
| `sources/base.py` | ✅ incremental `run()` |
| `sources/wasalt/scraper.py` | ✅ rewritten (HTTP + SQLite fallback) |
| `sources/bayut/scraper.py` | ✅ incremental (Algolia timestamp filter) |
| `sources/aqar/scraper.py` | ✅ incremental (early-stop) |
| `sources/haraj/scraper.py` | ✅ incremental (early-stop) |
| `sources/propertyfinder/scraper.py` | ✅ incremental (early-stop) |
| `dashboard/app.py` | ✅ Scraper Status section added |

## Rules added
- R12: Store all scraped listings in DB immediately via `save_opportunity()` in `base.run()`.
       Never rely on in-memory dedup across runs.
- R13: Each scraper must implement early-stop when N consecutive known IDs are encountered.
       Avoids re-fetching thousands of old listings on every run.

## Deferred
- WhatsApp session authentication (QR scan) — requires user interaction
- Wasalt web scraping (HTTP side) — blocked in Python; works in browser; will auto-activate on Linux/VPS
- Full end-to-end test: `python main.py --mode scrape` on Kali with Ollama running
- Additional platforms: Ejar.sa, OpenSooq — low priority (limited SA land listings)
