import sqlite3
import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path("db/agent.db")

def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            group_name TEXT,
            sender_phone TEXT,
            sender_name TEXT,
            raw_text TEXT,
            msg_type TEXT,
            property_type TEXT,
            city TEXT,
            district TEXT,
            area_sqm REAL,
            price_sar REAL,
            description TEXT,
            source TEXT DEFAULT 'whatsapp',
            timestamp TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS matches (
            id TEXT PRIMARY KEY,
            request_id TEXT,
            offer_id TEXT,
            match_score REAL,
            match_reasoning TEXT,
            broker_notified INTEGER DEFAULT 0,
            broker_action TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(request_id) REFERENCES messages(id),
            FOREIGN KEY(offer_id) REFERENCES messages(id)
        );

        -- source_url has a unique constraint enforced via INSERT OR IGNORE on id (listing_id)
        CREATE TABLE IF NOT EXISTS opportunities (
            id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            city TEXT,
            district TEXT,
            area_sqm REAL,
            price_sar REAL,
            contact_phone TEXT,
            contact_name TEXT,
            image_urls TEXT,
            source_url TEXT,
            analysis TEXT,
            financial TEXT,
            pdf_path TEXT,
            processed INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scraper_cursors (
            source TEXT PRIMARY KEY,
            last_run_at TEXT,
            last_listing_id TEXT,
            last_count INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_messages_type      ON messages(msg_type);
        CREATE INDEX IF NOT EXISTS idx_messages_city      ON messages(city);
        CREATE INDEX IF NOT EXISTS idx_messages_ts        ON messages(timestamp DESC);
        CREATE INDEX IF NOT EXISTS idx_matches_notified   ON matches(broker_notified);
        CREATE INDEX IF NOT EXISTS idx_matches_action     ON matches(broker_action);
        CREATE INDEX IF NOT EXISTS idx_opps_processed     ON opportunities(processed);
        CREATE INDEX IF NOT EXISTS idx_opps_source        ON opportunities(source);
        CREATE INDEX IF NOT EXISTS idx_opps_city          ON opportunities(city);
    """)
    conn.commit()

    # ── Schema migrations (safe: ALTER TABLE only if column missing) ──────────
    existing = {r[1] for r in conn.execute("PRAGMA table_info(opportunities)").fetchall()}
    migrations = [
        ("contact_name", "ALTER TABLE opportunities ADD COLUMN contact_name TEXT"),
    ]
    for col, sql in migrations:
        if col not in existing:
            conn.execute(sql)
    conn.commit()
    conn.close()

def save_message(msg: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO messages
        (id, group_name, sender_phone, sender_name, raw_text, msg_type,
         property_type, city, district, area_sqm, price_sar, description, source, timestamp)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        msg["message_id"], msg["group_name"], msg["sender_phone"],
        msg["sender_name"], msg["raw_text"], msg["msg_type"],
        msg.get("property_type"), msg.get("city"), msg.get("district"),
        msg.get("area_sqm"), msg.get("price_sar"), msg.get("description"),
        msg.get("source", "whatsapp"), msg["timestamp"]
    ))
    conn.commit()
    conn.close()

def save_match(match: dict):
    conn = get_conn()
    conn.execute("""
        INSERT OR IGNORE INTO matches
        (id, request_id, offer_id, match_score, match_reasoning)
        VALUES (?,?,?,?,?)
    """, (
        match["match_id"], match["request_id"], match["offer_id"],
        match["match_score"], match["match_reasoning"]
    ))
    conn.commit()
    conn.close()

def get_unmatched(msg_type: str, limit: int = 50) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(f"""
        SELECT * FROM messages
        WHERE msg_type = ?
        AND id NOT IN (
            SELECT {'request_id' if msg_type == 'request' else 'offer_id'} FROM matches
        )
        ORDER BY timestamp DESC LIMIT ?
    """, (msg_type, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pending_matches() -> list[dict]:
    conn = get_conn()
    rows = conn.execute("""
        SELECT m.*, 
               req.raw_text as req_text, req.sender_name as req_name,
               req.sender_phone as req_phone, req.city as req_city,
               req.price_sar as req_price, req.area_sqm as req_area,
               off.raw_text as off_text, off.sender_name as off_name,
               off.sender_phone as off_phone, off.city as off_city,
               off.price_sar as off_price, off.area_sqm as off_area
        FROM matches m
        JOIN messages req ON m.request_id = req.id
        JOIN messages off ON m.offer_id = off.id
        WHERE m.broker_notified = 0
        ORDER BY m.match_score DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def mark_match_notified(match_id: str):
    conn = get_conn()
    conn.execute("UPDATE matches SET broker_notified=1 WHERE id=?", (match_id,))
    conn.commit()
    conn.close()

def is_processed(lid: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM opportunities WHERE id=? AND processed=1", (lid,)).fetchone()
    conn.close()
    return bool(row)

def mark_processed(lid: str, status: str):
    conn = get_conn()
    # Ensure the row exists before updating (INSERT OR IGNORE is a no-op if already present)
    conn.execute(
        "INSERT OR IGNORE INTO opportunities (id, processed) VALUES (?, 0)",
        (lid,)
    )
    conn.execute("UPDATE opportunities SET processed=1 WHERE id=?", (lid,))
    conn.commit()
    conn.close()

def save_opportunity(opp: dict) -> bool:
    """INSERT OR IGNORE an opportunity. Returns True if a new row was inserted."""
    conn = get_conn()
    scraped_at = opp.get("scraped_at")
    if isinstance(scraped_at, datetime):
        scraped_at = scraped_at.isoformat()
    cur = conn.execute("""
        INSERT OR IGNORE INTO opportunities
        (id, source, title, city, district, area_sqm, price_sar,
         contact_phone, contact_name, image_urls, source_url, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        opp.get("listing_id"),
        opp.get("source"),
        opp.get("title"),
        opp.get("city"),
        opp.get("district"),
        opp.get("area_sqm"),
        opp.get("price_sar"),
        opp.get("contact_phone"),
        opp.get("contact_name"),
        opp.get("image_urls"),
        opp.get("source_url"),
        scraped_at or datetime.now().isoformat(),
    ))
    conn.commit()
    inserted = cur.rowcount > 0
    conn.close()
    return inserted

def listing_exists(listing_id: str) -> bool:
    """Return True if a listing with this id already exists in opportunities."""
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM opportunities WHERE id=?", (listing_id,)).fetchone()
    conn.close()
    return bool(row)

def update_opportunity_analysis(lid: str, analysis: dict, financial: dict, pdf_path: str = None):
    """Persist Ollama analysis + ROI results back to the opportunity row."""
    conn = get_conn()
    conn.execute("""
        UPDATE opportunities
        SET analysis  = ?,
            financial = ?,
            pdf_path  = ?,
            processed = 1
        WHERE id = ?
    """, (
        json.dumps(analysis,  ensure_ascii=False),
        json.dumps(financial, ensure_ascii=False),
        pdf_path,
        lid,
    ))
    conn.commit()
    conn.close()

def get_opportunities(limit: int = 50) -> list[dict]:
    """Return processed opportunities with analysis data, newest first."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM opportunities WHERE processed=1 ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_source_stats() -> list[dict]:
    """Return per-source counts and last-seen timestamps."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT source, COUNT(*) AS count, MAX(created_at) AS last_seen
        FROM opportunities
        GROUP BY source
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_cursor(source: str) -> dict:
    """Return the stored cursor for a source, or an empty dict if not found."""
    conn = get_conn()
    row = conn.execute(
        "SELECT last_run_at, last_listing_id, last_count FROM scraper_cursors WHERE source=?",
        (source,)
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {}

def set_cursor(source: str, last_listing_id: str, count: int):
    """UPSERT a cursor entry for a source."""
    conn = get_conn()
    conn.execute("""
        INSERT INTO scraper_cursors (source, last_run_at, last_listing_id, last_count)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            last_run_at     = excluded.last_run_at,
            last_listing_id = excluded.last_listing_id,
            last_count      = excluded.last_count
    """, (source, datetime.now().isoformat(), last_listing_id, count))
    conn.commit()
    conn.close()
