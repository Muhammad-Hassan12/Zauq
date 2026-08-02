# Implementation Plan — Zauq (AgenticEra Hybrid AI Discord Bot)

**Target environment:** Google Antigravity IDE (Remote SSH → Contabo VPS)
**Execution model:** Agent-executable, phase-gated. Complete and verify each phase before starting the next.
**Author:** Hassan / AgenticEra Systems
**Version:** 2.0 — supersedes v1.0 (replaces automatic model-cascade with explicit tier-selection)

---

## 0. Architecture Snapshot (context for the agent)

- **Bot framework:** `discord.py` (bot process) → thin client, all logic lives behind FastAPI, connects via Gateway (WebSocket) — **no domain/public URL required**
- **Backend:** FastAPI, `httpx` for outbound calls (no OpenAI/Gemini SDKs except where noted)
- **Model tiers — explicitly selected, not auto-cascaded (see §1.2):**
  - **Tier 1** — Gemini 2.5 Flash *or* DigitalOcean Gradient Serverless Inference (e.g. `llama3.3-70b-instruct`), switchable live via `/model` command
  - **Tier 2** — local model on the VPS via Ollama (`qwen3.5:4b`), explicitly locked when selected — no silent fallback to Tier 1
  - **Tier 3** — Kaggle T4-tunneled Qwen3.5 (larger variant), not always-on; explicit selection triggers a health-check/wake before use
- **Database/memory:** Supabase (Postgres + pgvector) — reuse existing project
- **Process management:** PM2 + Nginx, same pattern as existing AgenticEra services
- **Sandboxing:** Local Docker containers (not E2B)
- **TTS:** `edge-tts` primary, Coqui TTS offline fallback
- **No Redis/Celery/BullMQ/LangGraph in v1**

---

## Phase 0 — Foundations & Compliance

**Goal:** Discord app exists, repo is scaffolded, infra is provisioned, legal/policy boxes are checked. No bot logic yet.

### Tasks
- [ ] Create Discord application "Zauq" at `discord.com/developers/applications`
- [ ] Bot tab → Add Bot → copy token → `.env` as `DISCORD_BOT_TOKEN` (never commit)
- [ ] Bot tab → enable only needed intents: **Message Content**, and **Server Members** if using join/leave events
- [ ] OAuth2 tab → URL Generator → scopes `bot` + `applications.commands` → select required bot permissions (Send Messages, Read Message History, Use Slash Commands, Connect/Speak for later voice/TTS) → generate invite URL, authorize into your own server
- [ ] Scaffold repo structure:
  ```
  zauq-discord-bot/
  ├── bot/                 # discord.py client, slash commands, event handlers
  ├── backend/             # FastAPI app — all agent/model logic
  │   ├── routers/
  │   ├── agents/
  │   ├── memory/
  │   └── models/          # provider adapters: gemini, do_serverless, ollama, kaggle
  ├── infra/
  │   ├── pm2.config.js
  │   └── nginx.conf
  ├── PRIVACY.md
  └── plan.md
  ```
- [ ] Write `PRIVACY.md`: disclose providers that process messages (Gemini, DigitalOcean Gradient, self-hosted Qwen3.5-4B, Kaggle-tunneled Qwen3.5), what's stored, retention period, deletion process
- [ ] Confirm no message content is ever used to fine-tune/train any model — logging is for debugging/memory only
- [ ] Provision Supabase tables (schemas listed per-phase below)
- [ ] Install Ollama on Contabo VPS, pull `qwen3.5:4b`, verify with `ollama run qwen3.5:4b "hello"`
- [ ] Generate DigitalOcean Gradient model access key (console → API → GenAI scope), store as `DO_MODEL_ACCESS_KEY`
- [ ] Add bot + backend processes to PM2 ecosystem file alongside existing AgenticEra services

### Exit criteria
Bot appears online in your server, Ollama responds locally, DO key is valid (test curl against `https://inference.do-ai.run`), Supabase tables exist, `PRIVACY.md` committed.

---

## Phase 1 — Core Chat Engine (Dual-Mode Router + Explicit Tier Selection + Streaming + Memory)

**Goal:** A working, streaming, memory-aware chatbot with full manual control over which model tier and provider serves each channel. Ship this before touching RAG, code exec, or media gen.

### 1.1 Dual-mode context router
- [ ] `guild_configs` table: `guild_id`, `guild_name`, `default_mode` (`dev` | `hangout`)
- [ ] `channel_profiles` table: `channel_id`, `guild_id`, `operating_mode`, `system_persona_prompt`, `temperature`, tool permission flags
- [ ] Middleware resolves `channel_profiles` → falls back to `guild_configs.default_mode` → hardcoded default
- [ ] Seed two personas: **Dev mode** (concise, low temp ~0.2), **Hangout mode** (configurable persona, temp ~0.7–0.9)

### 1.2 Explicit tier-selection model routing (replaces auto-cascade)

**Design principle:** whatever tier/provider is explicitly selected serves *every* request until changed. No silent fallback, no automatic escalation.

- [ ] `model_selection` table (Supabase): `channel_id`, `tier` (`1`|`2`|`3`), `provider` (`gemini`|`digitalocean`|`ollama`|`kaggle`), `model_name`, `updated_at`, `updated_by`
- [ ] Provider adapters in `backend/models/`:
  - `gemini_client.py` — `httpx`-based, native Gemini API format
  - `openai_compatible_client.py` — single adapter reused for **DigitalOcean Gradient Serverless Inference** (`https://inference.do-ai.run`, chat-completions format) **and** local **Ollama** (`localhost:11434`, also OpenAI-compatible) — just swap `base_url`/`model`/auth header
  - `kaggle_client.py` — hits your cloudflared-tunneled endpoint, includes a lightweight health-check/ping before dispatching a real request
- [ ] `/model` slash command with subcommands:
  - `/model set tier:1 provider:gemini` — or `provider:digitalocean model:llama3.3-70b-instruct` (autocomplete model list via DO's "list available models" endpoint)
  - `/model set tier:2` — locks channel to local Ollama `qwen3.5:4b`, no fallback
  - `/model set tier:3` — pings Kaggle tunnel first; if unreachable, replies clearly ("Tier 3 is offline right now") instead of silently failing or falling back
  - `/model status` — shows current tier/provider/model for the channel
- [ ] Router logic: read `model_selection` for the channel → dispatch directly to that adapter only → no cascade logic at all

### 1.3 Streaming + Discord UX
- [ ] Port the `DiscordStreamBuffer` class (debounced edits, 1950-char truncation, respects 5-edits/5s limit)
- [ ] `interaction.defer(thinking=True)` within 500ms on all slash commands
- [ ] Auto-splitter/attach-as-`.md` for long dev-mode outputs (code blocks)

### 1.4 Memory Layer 1 — working context
- [ ] In-process sliding window buffer per thread/channel (no Redis for v1)
- [ ] Auto-spawn a Discord Thread for multi-turn conversations

### 1.5 Memory Layer 2 — episodic user facts
- [ ] `user_memories` table: `memory_id`, `user_id`, `category`, `fact_content`, `embedding vector`, `confidence_score`, `created_at`
- [ ] Background worker (post-idle) extracts facts via JSON-schema-forced prompt → embeds → upserts
- [ ] Route extraction to whichever tier is currently selected for that channel — no separate hardcoded model for this

### Exit criteria
Bot replies correctly in both modes, `/model set` actually switches behavior live (verify by comparing responses across Gemini vs DO vs Ollama), Tier 3 correctly reports offline status when Kaggle isn't running, streaming respects rate limits, facts persist across sessions.

---

## Phase 2 — RAG (Server Lore) + Local Code Execution

**Goal:** Dev-mode gets real utility (code exec, doc/repo grounding); hangout-mode gets server-specific "lore" recall.

### 2.1 Server Lore / Knowledge Base (Memory Layer 3)
- [ ] `server_lore` table: `guild_id`, `source_type` (`repo`|`doc`|`inside_joke`|`rule`), `content`, `embedding`
- [ ] Ingestion: chunk + embed repo docs/READMEs for dev servers; `/remember <fact>` command for hangout servers
- [ ] Retrieval: pgvector similarity search scoped to `guild_id`, inject top-k into system prompt

### 2.2 Sandboxed code execution (dev mode only)
- [ ] Local Docker sandbox runner — ephemeral container per execution, no network access, resource/time limits
- [ ] Support Python/JS/Bash; capture stdout/stderr/exit code/execution time
- [ ] Gate behind `channel_profiles.allow_code_exec`, off by default outside dev channels

### 2.3 GitHub integration (dev mode)
- [ ] Read-only GitHub API client (`httpx`) — PR diffs, stack-trace explanations, refactor suggestions inline in threads
- [ ] Scope to explicitly configured repos per guild

### Exit criteria
Dev-mode channel answers grounded in your project docs, executes code safely in Docker, explains pasted stack traces. Hangout-mode channel recalls facts via `/remember`.

---

## Phase 3 — Hangout Mode Polish (Media, Voice, Games)

**Goal:** Lowest technical priority, highest visibility for your own server. Ship after Phases 1–2 are stable.

### 3.1 Free TTS companion
- [ ] `edge-tts` for voice-channel summaries/commentary (primary, free, near-commercial quality)
- [ ] Coqui TTS as fully offline fallback
- [ ] Voice-channel join/leave logic, response queueing to avoid overlap

### 3.2 Media generation
- [ ] Meme generator: local text-overlay rendering, no API cost
- [ ] AI image gen: evaluate against whichever tier/provider is active before committing to a paid endpoint

### 3.3 Mini-games
- [ ] Trivia engine using `server_lore` + general knowledge, Discord buttons for answers
- [ ] Simple text-RPG / code-guessing sessions as stretch goals

### Exit criteria
Voice narration, meme/image commands, and at least one working mini-game — none touching dev-mode cost budget.

---

## Phase 4 — Hardening & Open-Source Prep

**Goal:** Clean, safe state before wider release — either to more servers or as a public repo.

- [ ] Review `PRIVACY.md` against actual behavior, update if scope changed
- [ ] Per-guild rate limiting so one active server can't starve model quota/tokens for others
- [ ] Cost/latency logging dashboard: which tier/provider served each request, DO token spend tracking (since DO is metered, unlike Ollama)
- [ ] Discord verification review — only relevant past ~75-100 servers or public privileged-intent requests; not needed while it's your own server
- [ ] **If open-sourcing:** split all secrets into `.env.example`, audit for leaked Supabase keys/system prompts/internal infra references, do a clean history rewrite rather than exposing early WIP commits, keep AgenticEra-specific lore/config in a private layer not committed to the public repo

---

## Explicitly deferred / cut from v1 (revisit only if a real need emerges)
- Redis + Celery/BullMQ task queue
- E2B paid sandbox
- LangGraph/Pydantic AI orchestration framework
- Separate Postgres instance (Supabase covers this)
- Paid TTS (ElevenLabs) or paid image gen APIs
- Automatic model fallback/cascade (replaced by explicit `/model` tier selection in v2.0)
- Public landing page / OAuth dashboard (optional later addition, not required to run the bot)
