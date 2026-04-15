# Gate 1 - Scope (Rami)

## Feature

Matching reliability fix + baseline contract tests (Phase 1/2).

## Problem statement

Matching flow can fail silently because message rows were mapped incorrectly, causing runtime key mismatches.

## Proposed solution

Fix database row mapping to return named columns reliably and add baseline automated tests for classifier, matcher, and notifier contracts to prevent regression.

## Success criteria

- `run_matching()` can read `request_id` and `offer_id` without key errors.
- At least one deterministic unit test verifies successful request-offer matching.
- Baseline tests for classifier and notifier contract formatting pass.

## Out of scope

- End-to-end real WhatsApp phone delivery validation.
- Production deployment and infra-level monitoring.
- Model quality tuning for Arabic classification prompts.

## Smallest useful version

- Fix row mapping in `core/database.py`.
- Add one test module covering core Phase 1/2 contracts.

## Verdict

APPROVED

Reason: This is the smallest high-impact fix to unblock runtime matching and create immediate regression protection.
