# Agents Folder Guide

This folder contains role prompt templates used as governance artifacts.

Runtime/operational custom agents for VS Code Copilot are now in:
- .github/agents/rami-scope.agent.md
- .github/agents/tarek-design.agent.md
- .github/agents/omar-verify.agent.md
- .github/agents/layla-ship.agent.md
- .github/agents/kareem-gate-orchestrator.agent.md

Why this split:
- `agents/*.md` keeps historical templates and plain documentation.
- `.github/agents/*.agent.md` enables actual Custom Agent behavior in VS Code.
