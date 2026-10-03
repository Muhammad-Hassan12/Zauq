# 🤖 Zauq — Complete Master Guide & Documentation (v4.0.0 — Bounded Agentic Architecture)

**Zauq (ذوق)** is an enterprise-grade, state-of-the-art hybrid AI Discord companion built by **Syed Muhammad Hassan / AgenticEra Systems**. It features a high-performance **FastAPI backend engine**, a lightweight **`discord.py` thin client**, an isolated **Docker Sandbox Runner**, a **Bounded Agent Runtime**, a native **Model Context Protocol (MCP) Client**, **Research v2 live web intelligence**, true **vector-based semantic memory (pgvector)**, interactive **Human-in-the-Loop approval buttons**, and multi-provider AI model routing across **Google Gemini, Anthropic Claude, Alibaba Qwen, DeepSeek, DigitalOcean Gradient, and local Ollama**.

---

## 📐 1. Architecture Overview

Zauq is architected around decoupled, failure-isolated services:

1. **FastAPI Engine (`zauq-backend`)**: Listens on `http://127.0.0.1:8002`. Houses the bounded agent runtime, tool registry, chat orchestrator, multi-provider model router, vector semantic memory, search engine, media processors, and observability pipelines.
2. **Sandbox Runner (`zauq-sandbox-runner`)**: Dedicated, isolated microservice on `http://127.0.0.1:8001` with exclusive access to the Docker socket. The main backend does not have access to `/var/run/docker.sock`.
3. **Discord Gateway Bot (`zauq-bot`)**: Thin client connecting via WebSocket. Listens for user mentions, thread messages, voice notes, and 31 slash commands.
4. **Supabase PostgreSQL (`pgvector`)**: 768-dimensional vector store for L2 user episodic memory, L3 server lore RAG, cost audit logs, and pending approval action tickets.

```text
                     ┌───────────────────────────────────────────┐
                     │            Discord Gateway (WS)           │
                     │   Voice Notes · Messages · 31 Slash Cmds  │
                     └─────────────────────┬─────────────────────┘
                                           │
                          ┌────────────────▼────────────────┐
                          │      Zauq Bot (discord.py)      │
                          │   Buttons · Approvals · Voice   │
                          └────────────────┬────────────────┘
                                           │ HTTP (Port 8002)
                          ┌────────────────▼────────────────┐
                          │     FastAPI Backend Engine      │
                          │ Tool Registry · Agent Runtime   │
                          │ Serper Search · MCP Client      │
                          └──────┬──────────┬───────────┬───┘
                                 │          │           │
     Internal Authenticated HTTP │          │           │
          (X-Internal-Token)     │          │           │
        ┌────────────────────────▼───┐  ┌───▼───────┐   │
        │   Isolated Sandbox Runner  │  │  Ollama   │   │
        │ (Docker Socket Isolation)  │  │(Local VPS)│   │
        └────────────────────────────┘  └───────────┘   │
                                                        │
                                ┌───────────────────────▼───┐
                                │    Supabase pgvector      │
                                │(L2 Semantic + L3 Lore RAG)│
                                └───────────────────────────┘
```

---

## 🎭 2. Operating Modes & Persona Configuration

Zauq operates in two primary modes configured via `/mode` at either **Channel** or **Server** scope:

### 🛠️ Dev Mode (`dev`)
* **Focus**: Architecture, software engineering, debugging, code testing, and sandboxed code execution.
* **Temperature**: Low (~`0.2`) for maximum deterministic precision.
* **Persona**: Senior Software Engineer & Architect (precise, direct, highly technical).
* **Code Execution**: Enabled by default (`allow_code_exec = true`).
* **Auto-Code Testing**: Configurable per channel (`off`, `auto`, `always`).

### 💬 Hangout Mode (`hangout`)
* **Focus**: Casual server companion, banter, server lore recall, memes, voice TTS, trivia mini-games, voice-to-voice replies, and community engagement.
* **Temperature**: High (~`0.75`) for expressive, witty, and engaging responses.
* **Persona**: Expressive, funny, and friendly community companion.
* **Code Execution**: Disabled by default (`allow_code_exec = false`).

#### Operating Mode Commands:
```
/mode mode:dev scope:Server      -> Sets entire community default to Dev Mode
/mode mode:hangout scope:Channel -> Locks current channel to Hangout Mode
/mode_reset                      -> Clears channel override and reverts to community default
```

---

## 🧠 3. Universal Thinking Mode (`/thinking`)

Zauq supports **extended deep-thinking and reasoning mode**, togglable per channel by administrators across **all AI models**:

* **Gemini Models**: Allocates up to **16,384 dedicated thinking tokens** via Google's native `thinkingConfig` API budget.
* **Anthropic, Qwen, DeepSeek & DigitalOcean**: Injects Deep Chain-of-Thought (CoT) multi-phase reasoning directives and automatically expands output token bounds (up to 32k tokens).
* **Internal Scratchpads Hidden**: Any `<thought>` or `<think>` tags generated internally are automatically stripped before sending to Discord — only the polished final answer is delivered.

```
/thinking mode:on   -> Enable deep reasoning for this channel (all AI models)
/thinking mode:off  -> Disable thinking mode, return to fast standard output
```

---

## ⚡ 4. Explicit Model Tier Routing Engine

Unlike bots with arbitrary cascades, Zauq uses **explicit locking**: whatever tier and provider is configured serves every request for that channel or server until changed.

### Expanded Tier-1 Provider Catalog (v4.0.0)

| Tier | Provider Identifier | Provider Name | Models Available |
|---|---|---|---|
| **Tier 1** | `gemini` (alias `google`) | Google AI Studio | `gemini-2.5-flash` (Default), `gemini-2.5-pro`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3-pro-preview`, `gemma-4-26b-a4b-it` |
| **Tier 1** | `anthropic` | Anthropic Claude Direct | `claude-sonnet-4-5`, `claude-3-5-sonnet`, `claude-3-5-haiku` |
| **Tier 1** | `qwen` | Alibaba Qwen Direct | `qwen-turbo`, `qwen-plus`, `qwen-max` |
| **Tier 1** | `deepseek` | DeepSeek Direct | `deepseek-chat`, `deepseek-coder`, `deepseek-reasoner` |
| **Tier 1** | `digitalocean` | DigitalOcean Gradient | `glm-5.3`, `glm-5.2`, `kimi-k3`, `llama-4-maverick`, `llama3.3-70b-instruct`, `minimax-m2.5` |
| **Tier 2** | `ollama` | Local VPS Model | `qwen3.5:4b` (zero API cost) |
| **Tier 3** | `kaggle` | Kaggle T4 Tunnel | `qwen3.5-t4` (pings `/health` before locking) |

#### Model Management Commands:
```
/model status                               -> Check active tier, provider, model name, and inheritance scope
/model set tier:1 provider:gemini scope:Server -> Lock entire community default to Google Gemini 2.5 Flash
/model set tier:1 provider:anthropic model:claude-sonnet-4-5 scope:Channel -> Lock channel to Claude Sonnet 4.5
/model set tier:1 provider:deepseek model:deepseek-chat -> Lock channel to DeepSeek Chat
/model reset                                -> Clears channel override and reverts to community default
```

### ⚠️ Transparent Provider Fallback Notifications
If a secondary provider fails or hits rate limits, Zauq automatically falls back to **Gemini 2.5 Flash** and notifies the user with a transparent embed notification.

---

## 🤖 5. Bounded Agent Runtime & Tool System (v4 New)

When `AGENT_RUNTIME_ENABLED=true`, Zauq operates as a bounded state-machine agent:

```text
User Message ──► Capability Router ──► Tool Selection ──► Agent Runtime Loop (Max 4-6 Steps)
                                                                 │
                  ┌──────────────────────────────────────────────┴─────────────────────────────────┐
                  ▼                                              ▼                                 ▼
           web.search / fetch                               code.execute                 mcp.<server>.<tool>
         (Serper + Research v2)                         (Hardened Sandbox)               (External Protocol)
```

### Safety & Reliability Guarantees:
* **Strict Step Budgets:** Normal requests: **max 4 tool steps**; Deep search: **max 6 tool steps**; Global hard cap: **8 steps**.
* **Direct Answer Shortcut:** Queries that do not need tools make **0 tool calls**, responding with zero added latency.
* **Loop Detection (Duplicate Call Guard):** Blocks repeating identical tool calls with identical arguments.
* **Structured Error Handling:** Tool exceptions become structured observations, preventing crashes.
* **Output Character Capping:** Tool outputs are capped to `SANDBOX_MAX_OUTPUT_CHARS` (12,000 characters) before context injection.
* **Untrusted Content Fencing:** All external data is tagged with `[BEGIN UNTRUSTED TOOL DATA]` boundaries.

#### Agent Status & Discovery Commands:
```
/agent status -> High-level overview: runtime status, step budgets, search provider, and MCP connections
/agent tools  -> List all registered tools, their risk levels, origin (native vs MCP), and guild scopes
```

---

## 🔍 6. Production Web Search & Research Mode v2

Zauq v4 features an authoritative live search engine:

* **Dual Provider Architecture:** Production **Serper.dev** Google Search API with automatic **DuckDuckGo** fallback.
* **In-Memory TTL Caching:** Frequently searched queries are cached in memory (default 300s TTL).
* **SSRF-Safe Fetcher:** Follows redirect chains while strictly validating each hop against private networks, cloud metadata (`169.254.169.254`), and loopback addresses.
* **Research Mode v2 (Bounded Flow):**
  1. **Query Decomposition:** Strips conversational filler and expands multi-aspect search terms.
  2. **Parallel Page Fetching:** Fetches top sources concurrently under a concurrency semaphore (`WEB_FETCH_CONCURRENCY=3`).
  3. **Boilerplate & Excerpt Filtering:** Removes cookie notices, navigation headers, and extracts dense evidence blocks.
  4. **Markdown Citations:** Synthesizes verified markdown sources (`• [Title](url)`).

```
/search query:"FastAPI dependency injection patterns" category:all deep:True
```

---

## 📦 7. Code Sandbox & Docker Socket Isolation

Zauq executes user and agent code inside ephemeral, hardened Docker containers:

* **Docker Socket Isolation:** The main backend does not have access to `/var/run/docker.sock`. All execution requests are routed over internal authenticated HTTP to the dedicated `sandbox-runner` microservice.
* **Container Hardening:** `--network none`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--memory 256m`, `--cpus 0.5`, `--pids-limit 50`, `--read-only`, non-root user `65534:65534`.
* **Image Allowlist:** `python:3.11-slim`, `node:18-alpine`, `alpine:latest` (bash).
* **Automatic Code Testing Modes:**
  * `off`: Standard execution only when requested.
  * `auto`: Automatically test code if the user prompt requests testing or verification.
  * `always`: System prompt directive forces the model to test code via `code.execute` before final response.
* **1-Attempt Self-Repair Loop:** If code fails in Dev Mode, Zauq feeds stderr back into context for exactly 1 bounded repair attempt.

```
/run language:python code:print("Hello from Zauq Sandbox!")
```

---

## 🛡️ 8. Human-in-the-Loop Confirmation System

To prevent unintended side effects, Zauq implements a strict tool risk classification system:

| Risk Level | Description | Behavior |
|---|---|---|
| `read` | Read-only queries (`web.search`, `web.fetch`, read APIs) | Auto-executed |
| `write` | Creates or modifies resources (send message, create issue) | **Requires Human Confirmation** |
| `destructive` | Deletes or irreversibly mutates data | **Requires Human Confirmation** |
| `privileged` | Host/code execution (`code.execute`) | Requires channel permission allowlist |

### Interactive Approval Embed
When an agent attempts a `write` or `destructive` action:
1. The tool execution is suspended and staged in `pending_actions`.
2. Zauq posts an interactive Discord embed detailing the action, arguments, and risk level.
3. Features **Approve** and **Deny** buttons.
4. Only the user who initiated the request (or a Server Administrator) can click Approve.
5. Tickets automatically expire after **5 minutes** if unhandled.

---

## 🔌 9. Model Context Protocol (MCP) Client Layer

Zauq connects to external MCP servers to discover and invoke third-party tools:

* **Configuration:** Defined in `config/mcp_servers.json`.
* **Transports Supported:** `stdio` (local subprocesses) and `streamable_http` (remote HTTP endpoints).
* **Canonical Namespacing:** `mcp.<server_id>.<tool_name>`.
* **Guild Scoping:** Servers can restrict tools to designated Discord guild IDs (`allowed_guild_ids`).
* **Failure Isolation:** If an external MCP server disconnects, normal bot operations and other tools are unaffected.
* **Zero Overhead When Disabled:** Set `MCP_ENABLED=false` to consume zero memory or network resources.

```
/mcp status -> Check connectivity, latency, and tool counts for configured MCP servers
/mcp tools  -> List all MCP tools currently registered and available in the server
```

---

## 📊 10. Observability, Cost Tracking & VPS Protection

* **Token Tracking:** Automatically extracts input and output tokens for every turn.
* **Estimated Cost Calculation:** Records USD cost per request in `request_logs`.
* **VPS Protection Semaphores:**
  * Sandbox concurrency capped by `SANDBOX_MAX_CONCURRENCY=1`.
  * Web fetch concurrency capped by `WEB_FETCH_CONCURRENCY=3`.
  * MCP calls capped by `MCP_MAX_CONCURRENCY=4`.
* **Provider Circuit Breakers:** Protects against cascading failures when upstream APIs experience outages.
* **Admin Audit Dashboard (`/admin metrics`):** Live dashboard showing request counts, total tokens, average latency, and estimated cost.

---

## 🔒 11. Security Hardening & Secret Scrubbing

Zauq v4 includes comprehensive production security controls:

* **Secret Scrubbing Engine (`sanitize_secrets`):** API keys (`SERPER_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `QWEN_API_KEY`, `DEEPSEEK_API_KEY`, `DO_MODEL_ACCESS_KEY`, `SUPABASE_KEY`, `INTERNAL_API_KEY`) and standard token patterns (`Bearer ...`, `AIzaSy...`, `sk-ant-...`, `ghp_...`, Supabase JWTs) are scrubbed and replaced with `[REDACTED_SECRET]` before reaching model context or Discord replies.
* **Prompt Injection Defense:** Strict system instructions and untrusted data fencing ensure the model never executes instructions embedded in retrieved webpages or documents.
* **SSRF Defense:** Authoritative IP validation blocking private subnets, cloud metadata (`169.254.169.254`), and IPv4-mapped IPv6 across `web.fetch` and redirect chains.

---

## 📋 12. Complete Slash Command Catalog (31 Commands)

### 🤖 Agent & Subsystems
* `/agent status` — Inspect agent runtime flags, budgets, and subsystem health.
* `/agent tools` — Discover active tools, risk levels, and guild scoping.
* `/search` — Live web search with Serper & Research v2 evidence synthesis.
* `/run` — Execute Python, JavaScript, or Bash code in isolated Docker sandbox.
* `/mcp status` — Check connection health for external MCP servers.
* `/mcp tools` — List external MCP tools available in this guild.

### 🧠 Model & Reasoning
* `/model status` — View active AI tier, provider, model name, and inheritance scope.
* `/model set` — Configure provider and model for channel or server.
* `/model reset` — Reset channel override to community server default.
* `/thinking` — Toggle extended reasoning mode on or off.
* `/info` — View complete technical engine specifications and limits.

### 🎭 Operating Mode & Persona
* `/mode` — Set operating mode (`dev` or `hangout`) for channel or server.
* `/mode_reset` — Revert channel operating mode to community server default.

### 🎙️ Media & Generation
* `/say` — Convert text to speech using Microsoft Edge Neural TTS (19 voices).
* `/imagine` — Generate photorealistic images via Google Gemini.
* `/meme` — Render custom humorous memes with custom top and bottom captions.

### 🎮 Mini-Games & Community
* `/trivia` — Play interactive multi-category trivia games with timed buttons.
* `/tictactoe` — Challenge a friend or AI to Tic-Tac-Toe.
* `/rps` — Play Rock, Paper, Scissors against Zauq.
* `/coinflip` — Flip a coin with realistic random outcomes.
* `/roll` — Roll tabletop dice (e.g. 1d6, 2d20).
* `/joke` — Get a programming or general joke.

### 📈 Gamification & Utility
* `/profile` — View personal user stats, XP, level, and command counters.
* `/leaderboard` — Display the server-wide XP and reputation leaderboard.
* `/remind` — Schedule delayed reminder notifications.
* `/export` — Export conversation history as a formatted Markdown or JSON transcript.

### 🛡️ Administration & Privacy
* `/admin set_role` — Designate custom upper-role for bot management.
* `/admin config` — View server administration settings and roles.
* `/admin metrics` — View live API usage, token counts, and cost dashboard.
* `/admin purge_user_data` — Right to be forgotten (purge user memories from database).
* `/help` — Interactive help menu with category filters.

---

*Architected and maintained by Syed Muhammad Hassan / AgenticEra Systems — Zauq v4.0.0 Master Documentation*
