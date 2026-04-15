# Gate 2 - Design (Tarek + Omar scenarios)

## Architecture fit

The fix is local to persistence mapping and does not change public module boundaries.

Affected flow:

- `sources/whatsapp/bridge.py` -> `pipeline/classifier.py` -> `core/database.py` -> `pipeline/matcher.py` -> `pipeline/notifier.py`

## Schema/API changes

- No schema change.
- No migration needed.
- Internal behavior change only:
  - `get_conn()` now sets `sqlite3.Row`.
  - `get_unmatched()` and `get_pending_matches()` return proper named dictionaries.

## Silent failure modes flagged

1. Numeric-key row mapping can produce apparently valid dicts that fail downstream only at runtime.
2. Matching can return no output with no explicit exception if key lookups default to missing branches.
3. Contract tests without DB integration may miss mapping regressions.

## Omar test scenarios (written during design)

1. `SCN-MATCH-001`: request/offer records are returned with named keys including `id` and `raw_text`.
2. `SCN-MATCH-002`: deterministic high-score pair creates one match with correct request/offer ids.
3. `SCN-CLASS-001`: short WhatsApp text is always classified as `irrelevant`.
4. `SCN-CLASS-002`: valid JSON classification result maps into expected message fields.
5. `SCN-NOTIFY-001`: formatted match message includes score, names, and match id.

## Verdict

APPROVED
