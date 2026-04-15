# memory/rules.md (Append-only)

## 2026-04-15
- Seeded governance baseline rules R01-R08 from v3 process.
- Future Gate 6 updates must append new entries only; no deletions.

## 2026-04-15 (Session update)
- R09: Do not derive query row dictionaries from PRAGMA table_info indexes.
	Use sqlite3.Row mapping (or cursor.description) to avoid silent key mismatches.
	[Source: matcher path failed because get_unmatched returned numeric keys instead of column names]