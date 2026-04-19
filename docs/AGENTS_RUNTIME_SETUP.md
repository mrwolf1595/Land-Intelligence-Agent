# Agents Runtime Setup (VS Code Copilot)

## What was fixed

Operational custom agents were added under `.github/agents` so they can be invoked from the Copilot Agent picker and subagent orchestration.

## Available operational agents

- `Rami Scope`
- `Tarek Design`
- `Omar Verify`
- `Layla Ship`
- `Kareem Gate Orchestrator`

## How to use

1. Open Copilot Chat in Agent mode.
2. Choose one of the agents above from the agent picker.
3. Paste your artifact/feature summary.
4. For full cycle, choose `Kareem Gate Orchestrator`.

## Important behavior

- `Kareem Gate Orchestrator` runs Gate 1-5 logic in sequence.
- If `Omar Verify` returns `NO-SHIP`, final decision must be `NO-SHIP`.

## Notes

- Existing files under `agents/*.md` are templates and governance docs.
- Runtime activation depends on `.github/agents/*.agent.md` files.
