Read the file `land_agent_v2_prompt.md` in this directory carefully and fully.

Then output a **structured implementation plan** before writing any code.

The plan must include:

1. **Project structure** — list every file and folder you will create, with one-line description of each
2. **Technology decisions** — for each component, state which free/local tool you will use and why (no paid APIs: no Anthropic API, no Replicate, no SendGrid)
   - AI model: Ollama (Qwen2.5-7B or Llama3.2-3B)
   - Image generation: Stable Diffusion 1.5 via ComfyUI (must fit 4GB VRAM)
   - WhatsApp: whatsapp-web.js (free, session-based)
   - PDF: WeasyPrint + Jinja2
   - DB: SQLite
   - Dashboard: Streamlit
3. **Implementation phases** — break work into phases (Phase 0 setup, Phase 1 WhatsApp, Phase 2 matching, Phase 3 land pipeline, Phase 4 dashboard), with exact files created per phase
4. **Dependencies list** — final `requirements.txt` and `package.json` contents
5. **Configuration** — full `.env.example` with all required variables
6. **Risk flags** — any technical challenges you anticipate (VRAM limits, Arabic text, WhatsApp session, etc.) and how you will handle them
7. **Questions for user** — anything ambiguous in the spec that needs clarification before coding

Hardware context:
- Dell G15 5511, i7-11800H, RTX 3050 4GB VRAM, 32GB RAM
- Kali Linux primary OS
- Ollama already available (Qwen2.5-Coder-7B previously used)
- Existing scrapers for Aqar.fm and Wasalt in SQLite format

**Do NOT write any code yet. Output the plan only. Wait for user approval before proceeding.**
