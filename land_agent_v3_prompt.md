# 🏗️ Land Intelligence Agent v3
# Six-Gate Agentic Development Process
# 100% Free & Open Source — No Commercial APIs

---

## 📌 PROJECT OVERVIEW

A modular AI agent that:
1. Monitors Saudi real estate WhatsApp groups (whatsapp-web.js — free)
2. Classifies messages as REQUEST (طلب) or OFFER (عرض) using Ollama locally
3. Matches requests ↔ offers and notifies the broker (you) via WhatsApp
4. Scrapes listing platforms (Aqar.fm, Wasalt) for high-value land opportunities
5. Generates AI analysis + financial model + PDF proposal using local tools only
6. **Learns from every session and improves its own rules over time**

### Hardware
- Dell G15 5511, i7-11800H, RTX 3050 4GB VRAM, 32GB RAM, Kali Linux
- Windows VM for WhatsApp Web JS only (no GPU access in VM)
- Ollama + ComfyUI run on Kali Linux host, accessed via local network from VM

### No Paid APIs — Ever
- AI: Ollama (qwen2.5:7b)
- Images: ComfyUI + SD1.5 (--lowvram flag)
- WhatsApp: whatsapp-web.js (session-based, free)
- PDF: WeasyPrint + Jinja2
- DB: SQLite
- Dashboard: Streamlit

---

## 🏛️ AGENTIC GOVERNANCE — THE FOUR AGENTS

Every feature, fix, or architectural decision passes through 4 agents.
Inspired by: https://tactful.ai/blog/ai-disruption/how-i-used-19-ai-agents-to-ship

**CRITICAL RULE — INDEPENDENT SPAWNING:**
Each agent receives ONLY:
- Their role description and blind spots
- The artifact under review
- The evaluation question

Agents NEVER see each other's responses before writing their own.
No anchoring. No contamination. True independent review.

### Agent 1: Rami — Product Lead
```
Role: Scopes every feature. Writes Feature Brief before any code.
      Asks: "What are we building, why, and what's the smallest useful version?"
Voice: Direct, minimal. Pushes back on scope creep. Breaks ties.
Blind spots: Does not think about implementation complexity or compliance details.
Gate: Scope (Gate 1)
Verdict format: APPROVED / NEEDS_REVISION / BLOCKED + 2-sentence reason
```

### Agent 2: Tarek — Architect
```
Role: Reviews schema changes, API contracts, system boundaries.
      Asks: "Does this fit the existing system? Any silent failure modes?"
Voice: Precise, technical. References specific tables, functions, patterns.
Blind spots: Does not think about UX or business priorities.
Special rule: Must flag any pattern that could fail silently (learned from
             db.transaction() + neon-http incident — silent atomicity failure
             with 39/39 passing tests).
Gate: Design (Gate 2)
Verdict format: APPROVED / CONCERN[details] / BLOCKED[reason]
```

### Agent 3: Omar — QA & Ops (VETO POWER)
```
Role: Writes test scenarios DURING design (not after). Has absolute veto on shipping.
      If Omar says NO-SHIP, nothing ships. No exceptions. No overrides.
Voice: Binary. "PASS" or "FAIL". Lists every failing scenario by name.
Blind spots: Does not think about business value or timeline pressure.
Special rules:
  - Writes tests while design is open, not after code is locked
  - Customer-facing routes tested against deployed environment, not localhost
  - No feature exits Build without passing tests
Gate: Verify (Gate 4) — binary SHIP / NO-SHIP
Verdict format: [scenario list with PASS/FAIL] then SHIP or NO-SHIP
```

### Agent 4: Layla — End User (Broker / You)
```
Role: Evaluates every user-facing feature through one question:
      "Would I actually use this? Does this save me time or add steps?"
Voice: Practical, impatient. Speaks as the broker receiving WhatsApp notifications.
Blind spots: Does not think about system architecture or compliance.
Special focus: WhatsApp message format — is the match notification clear enough
              to act on in 10 seconds?
Gate: Ship (Gate 5) — spot-check on deployed output
Verdict format: USEFUL / CONFUSING / MISSING[what's missing]
```

---

## 🚪 THE SIX-GATE PROCESS

Every feature — no matter how small — passes all six gates sequentially.
"Small change" exemptions are BANNED. This rule exists because every failure
in previous projects came from deciding the process didn't apply to this
particular change. It always does.

### Gate 1: SCOPE — Should we build this?
```
Who: Rami (Product Lead)
Input: Feature request or idea
Output: Feature Brief containing:
  - Problem statement (one sentence)
  - Proposed solution (one paragraph)
  - Success criteria (measurable)
  - Out of scope (explicit)
  - Smallest useful version
Rule: No code written until Feature Brief is approved.
```

### Gate 2: DESIGN — How should it work?
```
Who: Tarek (Architect) + Omar writes test scenarios here
Input: Approved Feature Brief
Output:
  - Schema changes (if any) with migration plan
  - API/function signatures
  - Omar's test scenario list (written NOW, not after build)
  - ComfyUI workflow JSON (if mockup feature)
Rule: Omar writes tests during design. Tests written after code locks
      describe what was built. Tests written during design expose what was missed.
```

### Gate 3: BUILD — Implement
```
Who: Claude Code (you directing it)
Input: Approved design + Omar's test scenarios
Output: Working code + passing tests
Rule: Code without tests does not exit this gate.
      If a test fails, fix the code — not the test.
```

### Gate 4: VERIFY — Does it actually work? (Omar's Veto Gate)
```
Who: Omar (absolute veto)
Input: Built feature + test suite
Output: SHIP or NO-SHIP
Rules:
  - Every scenario from Gate 2 must run
  - Customer-facing routes tested on deployed environment (not localhost)
  - 39/39 passing tests is NOT sufficient if environment parity not confirmed
  - NO-SHIP means NO-SHIP — not "ship with known issues"
```

### Gate 5: SHIP — Deploy and validate
```
Who: Layla (end user spot-check)
Input: Deployed feature
Output: USEFUL / CONFUSING / MISSING
Rule: Layla tests the WhatsApp notification output specifically.
      If the broker can't act on a match notification in 10 seconds, it fails.
```

### Gate 6: LEARN — Process ships itself
```
Who: All 4 agents independently
Input: The shipped feature + any incidents
Output per agent:
  - What worked
  - What to improve
  - Surprises (especially silent failures)
  - Proposed rule changes
Rule: NEVER skip Gate 6. This is where the process improves.
     Every new rule added to RULES.md must reference the incident that created it.
```

---

## 📚 RULES.md — Enforcement Rules (Updated Every Gate 6)

This file grows over time. Every agent reads it before starting any session.
Format: Rule number | What | Why (incident reference)

```markdown
# RULES.md — Land Agent Enforcement Rules
# Updated: [date of last Gate 6]

## Architecture Rules
R01: Never use db.transaction() with a driver that doesn't guarantee atomicity.
     Test transaction boundaries under partial failure, not just happy path.
     [Source: silent data corruption after 39/39 passing tests]

R02: Customer-facing routes (WhatsApp notifications, shared links) must be
     tested against the deployed/live environment, not localhost.
     [Source: features working internally but broken for end user]

R03: Navigation and layout changes are NOT style fixes. They require full
     Gate 1-6 process regardless of apparent size.
     [Source: sidebar redesigned 3 times due to category error]

## Code Rules
R04: No code ships without tests. Test count is not the metric — scenario
     coverage is. Omar writes scenarios during Gate 2, not Gate 4.

R05: No abstraction layer ships without at least one consumer in the same release.
     [Source: unused foundation code shipped in v6]

## Process Rules
R06: "This change is too small for the process" is not a valid exemption.
     Every failure came from this exact decision.

R07: Agents review artifacts cold. Never include your opinion or prior agent
     verdicts in a spawn prompt. Anchoring defeats the purpose.

R08: Gate 6 is mandatory. Teams that skip retrospectives repeat their mistakes.
```

---

## 🧠 MEMORY SYSTEM — Session Files

Claude Code conversations don't retain state. Compensate with file-based memory.

### File: `memory/session_latest.md`
Updated after every Gate 6. Contains:
```markdown
# Session Memory — [date]
## What shipped
- [feature name]: [one-line description]
## What was learned
- [incident or observation]
## Rules added
- R0X: [new rule]
## Deferred
- [feature or fix deferred to next session]
## Current state
- Phases complete: [list]
- Known issues: [list]
- Next priority: [feature]
```

### File: `memory/rules.md`
Append-only. Every Gate 6 can add rules, never delete.

### File: `memory/decisions.md`
Architectural Decision Records (ADRs). Format:
```markdown
## ADR-001: Ollama over Claude API
Date: [date]
Decision: Use Ollama (qwen2.5:7b) locally instead of Anthropic API
Reason: Zero cost, runs on existing hardware, no internet dependency
Tradeoff: Slower inference, less capable on complex reasoning
Status: Active
```

---

## 🗂️ PROJECT STRUCTURE

```
land-agent/
├── main.py                        # Orchestrator (APScheduler)
├── config.py                      # Config + feature flags
├── .env                           # Local paths and ports
├── RULES.md                       # Enforcement rules (append-only)
│
├── memory/
│   ├── session_latest.md          # Latest session state
│   ├── decisions.md               # Architectural Decision Records
│   └── sessions/                  # Archive of all past sessions
│       └── [date]_session.md
│
├── core/
│   ├── database.py                # SQLite interactions
│   ├── models.py                  # Pydantic models
│   ├── logger.py                  # Structured logging
│   └── scheduler.py               # APScheduler loop definitions
│
├── sources/                       # Pluggable data sources
│   ├── base.py                    # BaseSource abstract class
│   ├── whatsapp/
│   │   ├── client.js              # Node.js WhatsApp Web JS bot
│   │   └── bridge.py              # FastAPI receiver from Node.js
│   ├── aqar/
│   │   └── scraper.py             # Read from existing Aqar SQLite (read-only)
│   └── wasalt/
│       └── scraper.py             # Read from existing Wasalt SQLite (read-only)
│
├── pipeline/
│   ├── classifier.py              # Ollama: classify message offer/request
│   ├── matcher.py                 # Ollama: score request-offer pairs
│   ├── analyzer.py                # Ollama: text-only land analysis + scoring
│   ├── mockup.py                  # ComfyUI REST API: SD1.5 txt2img
│   ├── financial.py               # Rule-based ROI calculator
│   ├── proposal.py                # WeasyPrint PDF generator
│   └── notifier.py                # Format + send WhatsApp to broker
│
├── agents/                        # Agent spawn prompts (one file per agent)
│   ├── rami_scope.md              # Gate 1 prompt template
│   ├── tarek_design.md            # Gate 2 prompt template
│   ├── omar_verify.md             # Gate 4 prompt template
│   └── layla_ship.md              # Gate 5 prompt template
│
├── dashboard/
│   └── app.py                     # Streamlit broker review UI
│
├── output/
│   ├── reports/                   # Generated PDFs
│   └── mockups/                   # ComfyUI images
│
├── db/
│   └── agent.db                   # Main SQLite DB
│
├── requirements.txt
└── package.json
```

---

## ⚙️ TECHNOLOGY DECISIONS

| Component | Tool | Reason |
|-----------|------|--------|
| AI classification/matching | Ollama qwen2.5:7b | Free, local, good Arabic |
| AI fast classification | Ollama qwen2.5:3b | Faster for simple tasks |
| Image generation | ComfyUI + SD1.5 | Fits 4GB VRAM with --lowvram |
| WhatsApp | whatsapp-web.js | Free, session-based |
| PDF | WeasyPrint + Jinja2 | Free, Arabic RTL with reshaper |
| Database | SQLite | No server, existing data format |
| Dashboard | Streamlit | Simple, free |
| Orchestration | APScheduler | Built into Python |

### Ollama Usage Pattern
```python
# Always use official library, never raw HTTP
from ollama import Client
client = Client(host="http://localhost:11434")  # or VM network IP

response = client.chat(
    model="qwen2.5:7b",
    messages=[{"role": "user", "content": prompt}],
    format="json",           # MANDATORY — prevents malformed output
    options={
        "temperature": 0.1,  # Low temp for structured tasks
        "num_gpu": 20,        # Partial GPU offload — leaves room for ComfyUI
    }
)
```

### ComfyUI Usage Pattern
```python
# Use REST API with workflow JSON — no custom scripts
import httpx, time

def run_mockup(positive_prompt: str) -> bytes:
    workflow = load_sd15_workflow(positive_prompt)
    r = httpx.post("http://localhost:8188/prompt", json={"prompt": workflow})
    prompt_id = r.json()["prompt_id"]
    return wait_for_output(prompt_id)

# ComfyUI must start with: python main.py --lowvram --listen 0.0.0.0
```

### VM Network Setup
```
Kali Linux host:
  - Ollama: port 11434
  - ComfyUI: port 8188
  - Python pipeline + Streamlit

Windows VM:
  - WhatsApp client.js only
  - Sends messages to Python bridge on Kali IP

.env on Kali:
  OLLAMA_API_URL=http://localhost:11434
  COMFYUI_API_URL=http://localhost:8188

.env on Windows VM:
  PYTHON_BRIDGE_URL=http://192.168.x.x:3002/message
```

---

## 📋 requirements.txt

```
ollama>=0.2.0
httpx>=0.27.0
python-dotenv>=1.0.0
streamlit>=1.35.0
pandas>=2.2.0
pillow>=10.0.0
pydantic>=2.0.0
apscheduler>=3.10.0
fastapi>=0.110.0
uvicorn>=0.29.0
weasyprint>=60.0
jinja2>=3.1.0
arabic-reshaper>=3.0.0
python-bidi>=0.4.2
```

## 📦 package.json

```json
{
  "name": "land-agent-whatsapp",
  "version": "1.0.0",
  "main": "sources/whatsapp/client.js",
  "scripts": { "start": "node sources/whatsapp/client.js" },
  "dependencies": {
    "whatsapp-web.js": "^1.23.0",
    "qrcode-terminal": "^0.12.0",
    "express": "^4.18.0",
    "axios": "^1.6.0"
  }
}
```

---

## 🔐 .env.example

```env
# ── Local AI (on Kali host) ────────────────
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_MODEL_FAST=qwen2.5:3b
COMFYUI_API_URL=http://localhost:8188
SD_CHECKPOINT=v1-5-pruned-emaonly.ckpt

# ── WhatsApp ───────────────────────────────
BROKER_WHATSAPP=+966XXXXXXXXX
WA_BRIDGE_PORT=3001
PYTHON_BRIDGE_PORT=3002
WA_MONITORED_GROUPS=جروب عقارات جدة,عقارات الرياض,فرص عقارية الدمام

# ── Coverage ───────────────────────────────
TARGET_CITIES=جدة,الرياض,الدمام,مكة,المدينة,الطائف,أبها,تبوك,القصيم,حائل,جازان,نجران,الجوف,الخبر,القطيف

# ── Filters ────────────────────────────────
PRICE_MIN_SAR=500000
PRICE_MAX_SAR=3750000
MIN_MATCH_SCORE=0.65
MIN_OPPORTUNITY_SCORE=6.0

# ── Existing Scrapers (read-only) ──────────
AQAR_DB_PATH=/mnt/Kali desktop/Scraper_data/aqar.db
WASALT_DB_PATH=/mnt/Kali desktop/Scraper_data/wasalt.db

# ── Financial Benchmarks (SAR/sqm) ─────────
CONSTRUCTION_COST_APARTMENTS=2200
CONSTRUCTION_COST_VILLAS=2800
SELL_PRICE_APARTMENTS_SQM=6500
SELL_PRICE_VILLAS_SQM=5800

# ── Features ───────────────────────────────
FEATURE_WHATSAPP_MONITOR=true
FEATURE_PLATFORM_SCRAPING=true
FEATURE_AI_MOCKUP=true
FEATURE_PDF_PROPOSAL=true
FEATURE_AUTO_MATCH=true
```

---

## ✅ IMPLEMENTATION CHECKLIST (Phase by Phase)

### Phase 0 — Foundation
- [ ] Create full directory structure including `memory/` and `agents/`
- [ ] Write `core/database.py` + `core/models.py`
- [ ] Write `config.py` with feature flags
- [ ] Create `RULES.md` with R01-R08 pre-loaded
- [ ] Create `memory/session_latest.md` with empty template
- [ ] Create `memory/decisions.md` with ADR-001 (Ollama decision)
- [ ] Write `requirements.txt` + `package.json`
- [ ] **Gate 6**: Record Phase 0 decisions in session file

### Phase 1 — WhatsApp Pipeline
- [ ] **Gate 1 (Rami)**: Feature Brief for WhatsApp monitor
- [ ] **Gate 2 (Tarek + Omar)**: Design bridge architecture + write test scenarios
- [ ] **Gate 3**: Implement `client.js` + `bridge.py` + `classifier.py`
- [ ] **Gate 4 (Omar)**: Verify classification on 20 sample messages
- [ ] **Gate 5 (Layla)**: Is the message format actionable in 10 seconds?
- [ ] **Gate 6**: Update `RULES.md` + `session_latest.md`

### Phase 2 — Matching Engine
- [ ] **Gate 1 (Rami)**: Feature Brief for matcher + notifier
- [ ] **Gate 2 (Tarek + Omar)**: Design match scoring + notification format
- [ ] **Gate 3**: Implement `matcher.py` + `notifier.py`
- [ ] **Gate 4 (Omar)**: Verify matching with mock request/offer pairs
- [ ] **Gate 5 (Layla)**: Test real WhatsApp notification received and readable
- [ ] **Gate 6**: Update memory files

### Phase 3 — Land Opportunity Pipeline
- [ ] **Gate 1 (Rami)**: Feature Brief for scraper integration + analysis
- [ ] **Gate 2 (Tarek + Omar)**: Design analyzer + financial model + PDF
- [ ] **Gate 3**: Implement `analyzer.py` + `financial.py` + `mockup.py` + `proposal.py`
- [ ] **Gate 4 (Omar)**: Verify on 5 real listings from existing SQLite
- [ ] **Gate 5 (Layla)**: Is the PDF proposal useful? Would you send it?
- [ ] **Gate 6**: Update memory files

### Phase 4 — Orchestration + Dashboard
- [ ] **Gate 1 (Rami)**: Feature Brief for scheduler + dashboard
- [ ] **Gate 2 (Tarek + Omar)**: Design scheduler intervals + dashboard views
- [ ] **Gate 3**: Implement `main.py` + `dashboard/app.py`
- [ ] **Gate 4 (Omar)**: End-to-end test: WhatsApp message → match → broker notified
- [ ] **Gate 5 (Layla)**: Full workflow from broker perspective
- [ ] **Gate 6**: Full retrospective — what worked, what to add next

---

## ⚠️ RISK FLAGS

| Risk | Mitigation |
|------|-----------|
| VRAM 4GB: Ollama + ComfyUI concurrent | `--lowvram` + `num_gpu: 20` (partial offload) |
| Ollama malformed JSON | `format="json"` always + try/except + regex `\{.*\}` fallback |
| Silent failure modes (R01) | Test transaction boundaries under partial failure explicitly |
| Arabic in WeasyPrint | arabic-reshaper + python-bidi + Amiri font pre-render |
| WhatsApp session disconnect | Auto-reconnect in client.js + broker WhatsApp alert |
| DB path with spaces | Use `pathlib.Path()` always, never string concat |
| Localhost vs deployed gap (R02) | WhatsApp notification output tested on real phone, not terminal |

---

## 📝 AGENT SPAWN PROMPT TEMPLATES

### agents/rami_scope.md
```
You are Rami, Product Lead for a Saudi real estate AI agent built by a solo developer.

Your role: Scope features. Write Feature Briefs. Push back on scope creep.
Your blind spots: You do not think about implementation complexity or compliance.

RULES (read before responding):
[paste current RULES.md content here]

CURRENT PROJECT STATE:
[paste memory/session_latest.md here]

FEATURE REQUEST:
[paste request here]

Write a Feature Brief containing:
1. Problem statement (one sentence)
2. Proposed solution (one paragraph)
3. Success criteria (measurable)
4. Explicitly out of scope
5. Smallest useful version

End with: APPROVED / NEEDS_REVISION / BLOCKED + 2-sentence reason.
Do NOT look up other agents' opinions. This is your independent assessment.
```

### agents/omar_verify.md
```
You are Omar, QA & Operations Lead. You have absolute veto power on shipping.
If you say NO-SHIP, nothing ships. No exceptions. No overrides by anyone.

Your role: Write test scenarios during design. Verify builds. Block bad releases.
Your blind spots: You do not think about business value or timeline pressure.

CRITICAL RULES:
- R01: Test transaction boundaries under partial failure, not just happy path
- R02: Customer-facing output (WhatsApp messages) tested on real device, not terminal
- R04: No code ships without tests passing
- A feature with 39/39 passing tests can still be a NO-SHIP if environment
  parity is not confirmed.

ARTIFACT UNDER REVIEW:
[paste feature + test results here]

List every test scenario with PASS or FAIL.
Then give a single verdict: SHIP or NO-SHIP.
If NO-SHIP, list every blocking issue by name.
Do NOT consider timeline or business priority. Only: does it work correctly?
```

---

## 🚀 HOW TO RUN

```bash
# Kali Linux — start AI services
ollama serve
# In ComfyUI directory:
python main.py --lowvram --listen 0.0.0.0

# Install Python deps
pip install -r requirements.txt --break-system-packages

# Install Node deps (on Windows VM)
npm install

# First WhatsApp connection (Windows VM)
node sources/whatsapp/client.js
# Scan QR → session saved → Ctrl+C → session persists

# Run agent (Kali)
python main.py --mode all

# Dashboard (Kali, separate terminal)
streamlit run dashboard/app.py

# Mode options
python main.py --mode monitor   # WhatsApp only
python main.py --mode scrape    # Platforms only
python main.py --mode match     # Matching only
```

---

## 🔑 KEY PRINCIPLES (from production experience)

1. **The process applies to every change.** "This is too small" is how bugs ship.
2. **Independent spawning prevents anchoring.** Agents review cold or not at all.
3. **Omar's veto is absolute.** 39/39 passing tests can still be a NO-SHIP.
4. **Gate 6 is not optional.** It is where the system gets smarter.
5. **Memory files are the brain.** Claude Code has no memory — the files do.
6. **RULES.md grows, never shrinks.** Every rule references the incident that created it.
7. **Test where the user is.** WhatsApp notifications tested on a real phone.
