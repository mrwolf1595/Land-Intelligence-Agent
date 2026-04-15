# Gate Artifacts

This folder stores independent Gate 1-5 artifacts for each feature cycle.

## Folder naming

Use one folder per cycle:

- `YYYY-MM-DD_feature-slug/`

Example:

- `2026-04-15_feature_matching-reliability-tests/`

## Required files per cycle

- `GATE_1_SCOPE.md`
- `GATE_2_DESIGN.md`
- `GATE_3_BUILD.md`
- `GATE_4_VERIFY.md`
- `GATE_5_SHIP.md`

## Independence rule

Each gate artifact must only include:

- Artifact under review
- Evaluation question
- Single-agent verdict

Do not include other agent opinions in the same gate file.

## Reuse

Start every new cycle by copying:

- `_template/GATE_CYCLE_TEMPLATE.md`
