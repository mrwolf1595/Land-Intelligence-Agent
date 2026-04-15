# RULES.md — Land Agent Enforcement Rules
# Updated: 2026-04-15

## Architecture Rules
R01: Never use db.transaction() with a driver that does not guarantee atomicity.
Test transaction boundaries under partial failure, not only happy path.
[Source: silent data corruption incident after tests passed]

R02: Customer-facing routes (WhatsApp notifications, shared links) must be
tested against the deployed/live environment, not localhost.
[Source: features worked internally but failed for end users]

R03: Navigation and layout changes are not style-only changes.
They must pass Gate 1-6 with no exemptions.
[Source: repeated sidebar redesign regressions]

## Code Rules
R04: No code ships without tests. Scenario coverage matters more than test count.
Omar writes scenarios during Gate 2, not after build.

R05: No abstraction layer ships without at least one consumer in the same release.
[Source: unused foundation code shipped and increased maintenance overhead]

## Process Rules
R06: "This change is too small for the process" is never a valid exemption.
[Source: prior incidents caused by skipping process on "small" changes]

R07: Agents review artifacts cold. Spawn prompts must not include prior opinions
or verdicts from other agents.
[Source: anchoring contamination in multi-agent reviews]

R08: Gate 6 is mandatory. Retrospective outputs must be recorded every cycle.
[Source: repeated mistakes when retrospectives were skipped]

R09: Do not derive query row dictionaries from PRAGMA table_info indexes.
Use sqlite Row mapping (or cursor.description) for stable column names.
[Source: matcher runtime failure from numeric-key row mapping]