<div align="center">

<img src="assets/Zauq_Logo.png" alt="Zauq Logo" width="180px" style="border-radius: 20px; margin-bottom: 15px;" /><br />

# 🤖 Zauq (ذوق) — Bounded Agentic AI Discord Platform

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Discord.py](https://img.shields.io/badge/Discord.py-2.3%2B-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io)
[![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Docker](https://img.shields.io/badge/Docker-Sandbox-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![Claude](https://img.shields.io/badge/Claude-Sonnet%203.7-D97706?style=for-the-badge&logo=anthropic&logoColor=white)](https://anthropic.com)
[![MCP](https://img.shields.io/badge/MCP-Standard-8B5CF6?style=for-the-badge)](https://modelcontextprotocol.io)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge)](https://opensource.org/licenses/Apache-2.0)
[![Version](https://img.shields.io/badge/Version-4.0.0-FF6B6B?style=for-the-badge)](https://github.com/Muhammad-Hassan12/Zauq)

*A production-grade, bounded agentic AI Discord companion platform featuring native Tier-1 model routing (Claude 3.7, DeepSeek V3/R1, Qwen 2.5, Gemini 2.5 Pro), loop-bounded autonomous tool calling, Serper web search & Research Mode v2, isolated Docker sandbox code execution microservice, Model Context Protocol (MCP) tool integration, true vector-based semantic memory with decay, neural voice synthesis, free AI image generation, and interactive Discord human-in-the-loop approvals.*

</div>

---

## 🌟 Overview

**Zauq (ذوق)** is an enterprise-grade, bounded agentic AI Discord assistant created by **Syed Muhammad Hassan / AgenticEra Systems**. Engineered with a microservice architecture, Zauq decouples high-throughput Discord WebSocket events from AI reasoning, autonomous tool dispatch, and sandboxed code execution.

Zauq v4.0.0 introduces a **Bounded Agent Runtime**: models can dynamically plan, execute local and remote tools, inspect outputs, and self-correct across multi-turn reasoning loops. Every execution is strictly governed by deterministic step budgets, cycle loop detection, and Discord interactive human approvals for sensitive actions.

### What Makes Zauq v4.0.0 Unique?

* 🔄 **Bounded Agent Runtime**: Autonomous tool execution loop with deterministic step caps (1–8, default 4), cycle detection, call deduplication, and token limits.
* 🏛️ **Tier-1 Native Models**: Direct first-class support for **Anthropic Claude 3.7 Sonnet & 3.5 Haiku**, **DeepSeek V3 & R1**, **Qwen 2.5 & QwQ**, and **Google Gemini 2.5 Pro & Flash**, alongside local **Ollama** and **Kaggle T4** workers.
* 🌐 **Serper Search & Research Mode v2**: Real-time Google search grounding powered by Serper.dev, automated Jina Reader full-page extraction, and multi-query decomposition without recursive runaway loops.
* 🐳 **Docker Socket Isolation**: The backend has zero direct access to `/var/run/docker.sock`. Sandboxed code runs via a dedicated, air-gapped `sandbox-runner` microservice over an authenticated internal HTTP interface.
* 🔌 **Model Context Protocol (MCP)**: Standardized tool expansion supporting external MCP servers over StdIO and SSE with granular tool policy enforcement.
* 🛡️ **Human-in-the-Loop Approvals**: High-risk or mutating tool calls pause execution and prompt server administrators with interactive Discord UI buttons (`Approve` / `Reject`).
* 🧠 **True 3-Layer Vector Memory**: L1 active context, L2 user episodic memory (768-dim embeddings with cosine deduplication, contradiction tracking, and 24h decay), and L3 server lore RAG.
* 📄 **Universal Document & Media Ingestion**: Lossless parsing for `.pdf`, `.docx`, `.xlsx`, `.csv`, code files, audio waveforms (Urdu, Hindi, Arabic, English), and images up to 120,000 characters.

---

## 📐 Architecture & Workflow

Zauq v4.0.0 enforces a multi-tier decoupled topology where Discord event delivery, agentic reasoning, memory persistence, tool execution, and code sandboxing run in isolated fault domains:

```
                    ┌───────────────────────────────────────────┐
                    │            Discord Gateway (WS)           │
                    │  Voice Notes · Attachments · 31 Commands  │
                    └─────────────────────┬─────────────────────┘
                                          │
                         ┌────────────────▼────────────────┐
                         │     Zauq Bot (discord.py)       │
                         │   Approval UI · RBAC · XP       │
                         └────────────────┬────────────────┘
                                          │ HTTP (Internal HMAC)
                         ┌────────────────▼────────────────┐
                         │     FastAPI Backend Engine      │
                         │   Port 8002 · Bounded Runtime   │
                         └──────┬──────────┬───────────┬───┘
                                │          │           │
         ┌──────────────────────▼───┐   ┌──▼────────┐  └─────────────┐
         │   Supabase pgvector       │   │   MCP     │   ┌────────────▼────────────┐
         │(L2 Semantic + L3 Lore RAG)│   │  Servers  │   │  Sandbox Runner Service │
         └───────────────────────────┘   │(StdIO/SSE)│   │  Port 8003 (Docker Host)│
                                         └───────────┘   └────────────┬────────────┘
                                                                      │ Docker API
                                                         ┌────────────▼────────────┐
                                                         │ Isolated Docker Sandbox │
                                                         │ (--network none, tmpfs) │
                                                         └─────────────────────────┘
```

### Detailed Execution Pipeline

1. **Gateway Event Ingestion**: `bot/client.py` captures message events, user mentions, thread replies, attachments, or voice notes.
2. **Context & Document Parsing**: Attached files (`.pdf`, `.docx`, `.xlsx`, `.csv`, `.py`, images, audio) are decoded and parsed up to 120,000 characters (~30k tokens).
3. **Memory Retrieval**:
   - `episodic.py` queries Supabase `user_memories` via `match_user_memories` cosine similarity RPC.
   - `rag.py` queries `server_lore` via `match_server_lore` RPC for guild rules and lore.
4. **Unified Orchestration Dispatch (`backend/routers/chat.py`)**:
   - If Agent Runtime is enabled for the channel/server, execution passes to `backend/agent/runtime.py`.
   - Resolves model provider (Anthropic, DeepSeek, Qwen, Gemini, DO, Ollama, Kaggle).
5. **Bounded Tool Loop**:
   - Model analyzes query and available registered tools (`web_search`, `read_webpage`, `execute_code`, `remember_lore`, `mcp_*`).
   - If a tool requires human confirmation, an interactive Discord approval message is published; execution resumes upon admin click.
   - Loop detector monitors execution hash history: detects repeated identical tool calls or alternating cyclic loops.
   - Steps are capped strictly by `AGENT_MAX_STEPS` (default 4, hard max 8).
6. **Delivery & Auto-Chunking**: Response is formatted, thoughts sanitized, output code highlighted, files bundled (ZIP if multi-file), and auto-chunked into clean 1,900-character Discord messages.

---

## 🛠️ Technology Stack & Infrastructure

| Layer / Category | Technologies & Tools | Description / Role |
|---|---|---|
| **Bot Client** | `discord.py 2.3+`, `PyNaCl` | Async Discord WebSocket client, voice channels, 31 slash commands & UI interactive components |
| **API Backend Engine** | `FastAPI 0.100+`, `Uvicorn`, `Pydantic v2` | High-performance asynchronous REST & SSE backend engine on Port 8002 |
| **Agentic Runtime** | `Zauq Bounded Loop`, `ToolRegistry` | Step-bounded tool-calling agent runtime with cycle detection and human approval workflows |
| **Tier-1 AI Providers** | `Claude 3.7/3.5`, `DeepSeek V3/R1`, `Qwen 2.5`, `Gemini 2.5 Pro/Flash` | Native Tier-1 provider adapters with explicit routing and fallback notifications |
| **Search Engine** | `Serper.dev API`, `Jina Reader API` | Real-time Google Search grounding with concurrent full-page markdown scraping |
| **Vector Memory & Storage** | `Supabase PostgreSQL`, `pgvector` (768-dim) | 3-tier memory: L1 working context, L2 true semantic episodic memory, L3 server lore RAG |
| **Sandbox Isolation** | `FastAPI Runner (Port 8003)`, `Docker Engine` | Isolated microservice managing ephemeral non-root containers (`--network none`, read-only FS) |
| **Tool Extensibility** | `Model Context Protocol (MCP)` | Client support for external StdIO and SSE MCP tool servers with security policy filtering |
| **Multimodal Parsers** | `pypdf`, `python-docx`, `openpyxl`, `Pillow` | Lossless document parsing, table extraction, and local meme canvas rendering |
| **Voice Synthesis** | `Microsoft Edge Neural TTS (edge-tts)` | Free cloud neural voice synthesis across 19 voices and 8 global languages |
| **Security & Cryptography** | `HMAC`, `ipaddress`, `socket`, `hashlib` | Constant-time authentication, DNS-resolving SSRF defense, SHA-256 moderation logs |
| **Supervision & Deploys** | `Docker Compose`, `PM2`, `Python venv` | Containerized microservice composition or bare-metal multi-daemon supervision |

---

## 🚀 Key Features

### 🔄 1. Bounded Agentic Runtime & Deterministic Tool Calling *(v4.0.0 New)*
* **Deterministic Execution Budgets**: Prevents infinite loops and runaway API costs by bounding tool-calling cycles (`AGENT_MAX_STEPS=4`, hard ceiling of 8 steps).
* **Smart Loop Detection**: Graph cycle detector checks tool invocation histories. If repetitive or alternating cycles occur, the runtime terminates the loop and forces final answer synthesis.
* **Granular Tool Registry**: Built-in tools for live Google search, full-page webpage reading, isolated Python/Node/Bash code execution, server lore memory writing, and external MCP tool dispatch.
* **Channel & Server Scopes**: Enable agentic capabilities server-wide or confine them to dedicated testing channels (`/agent enable`).

### ⚡ 2. Native Tier-1 Multi-Model Provider Matrix *(v4.0.0 New)*
Zauq provides first-class, native SDK adapters for leading frontier models:
* **Anthropic (`anthropic`)**: `claude-3-7-sonnet-latest` (with extended thinking), `claude-3-5-haiku-latest`.
* **DeepSeek (`deepseek`)**: `deepseek-chat` (DeepSeek V3), `deepseek-reasoner` (DeepSeek R1).
* **Qwen (`qwen`)**: `qwen-max`, `qwen-plus`, `qwen-turbo`, `qwq-32b`.
* **Google AI Studio (`gemini` / `google`)**: `gemini-2.5-flash` (Default), `gemini-2.5-pro` (Thinking up to 16k tokens), `gemini-2.0-flash`.
* **DigitalOcean Gradient (`digitalocean`)**: Kimi K2.5/K3, GLM-5, Llama 3.3 70B, MiniMax.
* **Local VPS & GPU Tunnels**: Local Ollama (`qwen2.5:7b`, zero cost) and Cloudflared tunneled Kaggle T4 GPU workers.

### 🌐 3. Serper-Powered Web Search & Deep Research Mode v2 *(v4.0.0 New)*
* **Fast Google Grounding**: High-speed, authoritative search queries via the Serper.dev Google Search API.
* **Autonomous Intent Detection**: Live chat queries asking for current events, documentation, or real-time facts automatically invoke web search.
* **Deep Research Mode v2 (`/research`)**: Decomposes complex investigations into multi-angle queries, concurrently scrapes the top 3–5 sources via Jina Reader, synthesizes conflicting perspectives, and provides clean Markdown citations.
* **Domain & Category Filters**: Target searches directly to GitHub (`github`), ArXiv papers (`arxiv`), documentation (`docs`), Wikipedia (`wikipedia`), or News (`news`).

### 🐳 4. Isolated Sandbox Runner & Automated Code Testing *(v4.0.0 New)*
* **Decoupled Architecture**: The main backend container has no Docker socket mounted. Instead, code execution requests are forwarded to an internal `sandbox-runner` microservice over authenticated HTTP.
* **Ephemeral Container Jail**: Executes Python, Node.js, and Bash inside non-root containers (`nobody`, uid 65534) with `--network none`, `--read-only` rootfs, 256MB RAM caps, 0.5 CPU limits, and strict 5-second timeouts.
* **Automated Code Testing (`auto_code_test_mode`)**: When enabled for a channel (`/sandbox auto_test:on`), generated code snippets are tested inside the sandbox automatically before the bot posts the final response.

### 🔌 5. Model Context Protocol (MCP) Client *(v4.0.0 New)*
* **Standardized Tool Ingestion**: Connect external MCP servers running over `stdio` or `sse` directly to Zauq.
* **Tool Policy Filtering**: Granular configuration per tool (`ALLOW`, `REQUIRE_APPROVAL`, `BLOCK`). Read-only tools execute seamlessly; modifying tools require confirmation.
* **Dynamic Inspection**: Inspect registered MCP servers, exposed tools, and execution status using `/mcp list` and `/mcp health`.

### 🛡️ 6. Human-in-the-Loop Discord Approvals *(v4.0.0 New)*
* **Interactive UI Buttons**: Dangerous or mutating actions (e.g. database updates, write-level MCP tools, file modifications) pause the agent loop and display interactive **Approve** and **Reject** buttons in Discord.
* **RBAC Protected**: Only users with Server Administrator permissions or the designated Upper Role can authorize tool actions.
* **Timeout Resiliency**: Pending approvals cleanly expire after 60 seconds with an informative cancellation message.

### 🧠 7. Universal Extended Reasoning & Thinking Mode
* **Gemini Extended Thinking**: Dedicated reasoning budget (up to 16,384 thinking tokens) via native `thinkingConfig`.
* **Deep CoT Injection**: Deep Chain-of-Thought reasoning directives for open and frontier models with 65,536 token output window.
* **Sanitized Output**: Internal `<thought>` and `<think>` scratchpad blocks are automatically filtered from chat output.

### 🧬 8. True 3-Layer Semantic Vector Memory Architecture
* **L1 Working Memory**: 8-message conversational sliding context window.
* **L2 User Episodic Memory (`user_memories`)**:
  * 768-dimensional embeddings generated and stored for every extracted personal fact.
  * Semantic retrieval via `match_user_memories` pgvector RPC ranked by `similarity × importance_score`.
  * Cosine deduplication threshold (≥ 0.92) and contradiction detection.
  * 24-hour background memory worker applying a 5% decay per cycle to unaccessed memories and pruning facts below 0.15 importance.
* **L3 Server Lore RAG (`server_lore`)**: Guild-specific knowledge base, server rules, and ingested GitHub repository documentation retrieved via `match_server_lore`.

### 📄 9. Universal Document, Vision & Voice Note Ingestion
* **Voice Notes**: Native audio ingestion for Urdu, Roman Urdu, Hindi, Arabic, and English with fallback transcription.
* **Documents & Spreadsheets**: Lossless parsing for `.pdf` (page-by-page), `.docx` (tables + text), `.xlsx`, `.csv` (markdown table formatting) up to 120,000 characters.
* **Code & Text Files**: Parses `.py`, `.js`, `.ts`, `.html`, `.json`, `.sql`, `.sh`, `.md`, `.log` files directly.
* **Dynamic File Delivery**: Delivers complete, downloadable code/data files and automatically packages multiple created files into a `project_files.zip` archive.

### 🔊 10. Free Multi-Language Neural TTS & AI Image Studio
* **Neural TTS (`/tts`)**: 19 Microsoft Edge neural voices across 8 languages with zero API cost.
* **Voice Companion (`/voice join`)**: Connects to Discord voice channels for real-time speech responses.
* **AI Image Generation (`/image`)**: Free high-resolution image generation via Gemini Flash Image (`gemini-3.1-flash-image`) and DigitalOcean Gradient.
* **Meme Studio (`/meme`)**: Local Pillow canvas rendering classic Impact-font top/bottom memes.

### 🏆 11. XP Gamification, AI Content Moderation & Privacy
* **Activity XP**: Automated XP tracking (+1 per message, +2 per command, +5 per trivia win) with mathematical leveling.
* **AI Moderation (`/moderation`)**: Real-time message classification (`safe`, `borderline`, `toxic`) with automatic deletion and privacy-preserving SHA-256 hash audit logging.
* **GDPR Compliance (`/forget`, `/privacy`)**: Instant, permanent purging of stored user vector memories on user request.

---

## 📜 Complete Slash Command Reference (31 Commands)

| Command | Category | Scope / Permissions | Description |
|---|---|---|---|
| `/info` | Core | Everyone | View live system specifications, active model tier, mode, and backend health. |
| `/mode` | Core | Admin / Upper Role | Switch channel or server mode between `dev` and `hangout`. |
| `/mode_reset` | Core | Admin / Upper Role | Clear channel mode override and revert to community default. |
| `/summarize` | Core | Everyone | Summarize active thread or recent channel messages into concise bullet points. |
| `/thinking` | Core | Admin / Upper Role | Toggle extended deep reasoning mode (`on`/`off`) for the channel. |
| `/stats` | Analytics | Everyone | View server request volume, latency averages, and provider dispatch metrics. |
| `/model status` | Models | Everyone | View active model tier, provider name, and inheritance scope. |
| `/model set` | Models | Admin / Upper Role | Set model provider (Google Gemini, Claude, DeepSeek, Qwen, DO, Ollama, Kaggle). |
| `/model reset` | Models | Admin / Upper Role | Clear channel model override and revert to community server default. |
| `/search` | Search | Everyone | Perform live Serper web search with full-page extraction and citations. |
| `/research` | Search | Everyone | Conduct deep multi-query research with source synthesis and structured findings. |
| `/run` | Sandbox | Dev Mode / Allowed | Execute Python, Node.js, or Bash code in an ephemeral Docker container. |
| `/sandbox` | Sandbox | Admin / Upper Role | View runner status, test containers, or toggle `auto_test` mode. |
| `/file generate`| Files | Everyone | Generate complete, downloadable code or document files. |
| `/create_file` | Files | Everyone | Quick shortcut for on-demand code and document creation. |
| `/agent` | Agent | Admin / Upper Role | Inspect agent runtime status, configure step bounds, or toggle agent loop. |
| `/mcp` | Agent | Admin / Upper Role | List connected MCP servers, inspect tool policies, or check connection health. |
| `/approve` | Agent | Admin / Upper Role | Authorize or reject a pending human-in-the-loop tool execution. |
| `/remember` | Lore | Admin / Upper Role | Save a permanent rule or lore fact into Supabase L3 vector memory. |
| `/rank` | XP | Everyone | View your personal XP balance, level, rank, and progress bar. |
| `/leaderboard` | XP | Everyone | View the top 10 server members on the XP leaderboard. |
| `/remind` | Utility | Everyone | Schedule a reminder message delivered directly to chat or DM (1m–7d). |
| `/export` | Utility | Everyone | Export conversation history as a clean Markdown document. |
| `/github pr` | GitHub | Everyone | Fetch and summarize a GitHub Pull Request diff and discussion. |
| `/github issue`| GitHub | Everyone | Fetch and summarize a GitHub Issue. |
| `/ingest_repo` | GitHub | Admin / Upper Role | Ingest a GitHub repository README into server lore vector memory. |
| `/tts` | Voice | Everyone | Generate high-quality multi-language neural speech from text. |
| `/voice join` | Voice | Everyone | Connect Zauq to your current voice channel. |
| `/voice leave`| Voice | Everyone | Disconnect Zauq from the voice channel. |
| `/meme` | Media | Everyone | Render an image meme with Impact font styling. |
| `/image` | Media | Everyone | Generate AI artwork (Free Gemini Flash Image / DigitalOcean). |
| `/trivia` | Games | Everyone | Play an interactive trivia quiz with XP rewards and server lore integration. |
| `/moderation` | Admin | Admin Only | Configure AI content moderation (`enable`, `sensitivity`, `log`). |
| `/admin set_role`| Admin | Admin Only | Designate a custom Discord role with Zauq management privileges. |
| `/admin memory` | Admin | Admin Only | View vector memory statistics and token usage audits. |
| `/admin channels`| Admin | Admin Only | List all channels with custom overrides or profiles. |
| `/forget` | Privacy | Everyone | GDPR purge: permanently delete all stored episodic memories for your user. |
| `/privacy` | Privacy | Everyone | Display Zauq data privacy, retention, and storage policy. |
| `!sync` | Admin | Admin Only | Force instant synchronization of application slash commands. |

---

## 📂 Repository Structure

```
Zauq/
├── backend/
│   ├── config.py                 # Pydantic Settings & Environment Configuration
│   ├── main.py                   # FastAPI Application Entrypoint (Port 8002)
│   ├── logging_config.py         # Centralized Structured JSON/Text Logging
│   ├── agent/                    # Bounded Agentic Runtime (v4.0.0 New)
│   │   ├── runtime.py            # Bounded Tool Loop, Step Limiter & Token Tracker
│   │   ├── loop_detector.py      # Call Cycle & Repetition Detector
│   │   ├── approval.py           # Human-in-the-Loop Discord Approval Coordinator
│   │   └── tools/                # Registered Execution Tools
│   │       ├── registry.py       # Central Tool Registry & Policy Gating
│   │       ├── web_search.py     # Serper API Search Tool
│   │       ├── code_runner.py    # Sandbox Runner Dispatcher Tool
│   │       └── memory_tool.py    # Episodic & Lore Memory Ingestion Tool
│   ├── mcp/                      # Model Context Protocol Client (v4.0.0 New)
│   │   ├── client.py             # StdIO & SSE MCP Client Transport
│   │   ├── manager.py            # Server Lifecycles & Dynamic Discovery
│   │   └── policy.py             # Security Policy Enforcement (ALLOW / APPROVE / BLOCK)
│   ├── models/                   # Native Multi-Model Provider Adapters
│   │   ├── router.py             # 3-Tier Model Router & Explicit Provider Locking
│   │   ├── gemini_client.py      # Google Gemini 2.5 Pro/Flash Adapter (Thinking Mode)
│   │   ├── anthropic_client.py   # Native Anthropic Claude 3.7 / 3.5 Adapter (v4.0.0 New)
│   │   ├── deepseek_client.py    # Native DeepSeek V3 / R1 Adapter (v4.0.0 New)
│   │   ├── qwen_client.py        # Native Qwen 2.5 / QwQ Adapter (v4.0.0 New)
│   │   ├── openai_compatible_client.py # DigitalOcean Gradient & Ollama Adapter
│   │   └── kaggle_client.py      # Cloudflared Tunneled Kaggle GPU Worker Adapter
│   ├── memory/                   # 3-Layer Vector Memory Engine
│   │   ├── db.py                 # Async Supabase Client
│   │   ├── embeddings.py         # 768-dim Vector Embeddings (gemini-embedding-001)
│   │   ├── episodic.py           # L2 Semantic Memory: Dedup, Contradictions, Importance
│   │   ├── rag.py                # L3 Server Lore Retrieval (match_server_lore RPC)
│   │   ├── memory_worker.py      # 24h Background Memory Decay Worker
│   │   └── schema.sql            # Supabase pgvector Schema (M1 to M6 Migrations)
│   ├── sandbox/                  # Code Execution Client
│   │   └── runner_client.py      # HTTP Client for Isolated Sandbox Runner Service
│   ├── integrations/             # External Web & API Integrations
│   │   ├── serper_search.py      # Serper.dev Google Grounding & Jina Reader Client
│   │   └── github_client.py      # GitHub PR, Issue & Repo Ingestion Client
│   ├── media/                    # Voice & Image Generators
│   │   ├── tts.py                # Edge-TTS Neural Voice Synthesizer (19 Voices)
│   │   ├── gemini_image.py       # Free Gemini Flash Image Generator
│   │   └── meme_generator.py     # Pillow Local Canvas Meme Renderer
│   ├── moderation/               # Safety & Content Classification
│   │   └── content_filter.py     # AI Content Classifier (Safe / Borderline / Toxic)
│   └── routers/                  # FastAPI REST & SSE Route Handlers
│       ├── chat.py               # Unified Chat & Agent Orchestration Endpoint
│       ├── agent.py              # Agent Runtime Inspection & Configuration Endpoints
│       ├── mcp.py                # MCP Server & Tool Management Endpoints
│       ├── model.py              # Model Status, Autocomplete & Set Endpoints
│       ├── sandbox.py            # Code Execution Dispatch & Health Endpoints
│       └── admin.py              # Memory Stats, XP Leaderboard & Purge Endpoints
├── sandbox-runner/               # Isolated Docker Sandbox Microservice (v4.0.0 New)
│   ├── app.py                    # Lightweight FastAPI Daemon (Port 8003)
│   ├── executor.py               # Docker Subprocess Manager (--network none)
│   └── Dockerfile                # Dedicated Dockerfile with Docker CLI
├── bot/                          # Discord Gateway Thin Client
│   ├── client.py                 # Discord.py Gateway Client & Voice Handlers
│   ├── api.py                    # Centralized Backend API Client (HMAC Headers)
│   ├── auth.py                   # Upper-Role & Discord Permission RBAC
│   ├── stream_buffer.py          # Intelligent Multi-Message Auto-Chunking
│   ├── ui/                       # Interactive UI Components
│   │   └── approval_view.py      # Interactive Discord Approve/Reject Buttons
│   └── commands/                 # 31 Slash Command Handlers
│       ├── agent_slash.py        # /agent Status & Configuration
│       ├── mcp_slash.py          # /mcp Server Management
│       ├── approve_slash.py      # /approve Tool Execution Approval
│       ├── research_slash.py     # /research Deep Research Mode v2
│       ├── search_slash.py       # /search Web Grounding
│       ├── exec_slash.py         # /run Sandbox Execution
│       ├── sandbox_slash.py      # /sandbox Control & Auto-Test
│       ├── model_slash.py        # /model Selection & Status
│       └── ...                   # Core, Media, Voice, XP, and Admin commands
├── tests/                        # 7-Stage Comprehensive Pytest Suite
│   ├── unit/                     # Unit Tests for Parsers, Models & Logic
│   ├── integration/              # FastAPI Router & Endpoint Tests
│   ├── agent/                    # Agent Runtime, Loop Detection & Tool Tests
│   ├── mcp/                      # MCP Client & Policy Tests
│   ├── security/                 # SSRF, Auth & Rate Limiter Security Hardening
│   └── e2e/                      # End-to-End Workflow & Delivery Tests
├── docker-compose.yml            # 3-Container Orchestration (Backend, Bot, Sandbox-Runner)
├── Dockerfile.backend            # Container Image for FastAPI Backend
├── Dockerfile.bot                # Container Image for Discord Bot
├── requirements.txt              # Production Python Package Dependencies
├── .env.example                  # Comprehensive Environment Variables Template
├── DEPLOYMENT.md                 # Deployment & Infrastructure Guide
├── USER_GUIDE.md                 # Comprehensive User & Administrator Manual
├── CONTRIBUTING.md               # Developer Contribution & Testing Guidelines
├── LICENSE                       # Apache License 2.0
└── README.md                     # Master Documentation
```

---

## 🔧 Installation & Deployment

### 🐳 1-Click Docker Compose Deployment (Recommended)

The recommended production deployment runs three isolated containers: the **FastAPI Backend**, the **Discord Bot**, and the air-gapped **Sandbox Runner**.

1. **Clone the Repository**:
```bash
git clone https://github.com/Muhammad-Hassan12/Zauq.git
cd Zauq
```

2. **Configure Environment Variables**:
```bash
cp .env.example .env
nano .env
```
Fill in the essential credentials:
```env
DISCORD_BOT_TOKEN=your_discord_bot_token
BACKEND_HOST=backend
BACKEND_PORT=8002
INTERNAL_API_KEY=generate_a_random_64_character_hex_secret

# AI Model Keys (Configure at least one Tier-1 provider)
GEMINI_API_KEY=your_google_ai_studio_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
DASHSCOPE_API_KEY=your_qwen_dashscope_api_key

# Supabase Vector Memory
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_service_role_key

# Web Search
SERPER_API_KEY=your_serper_dev_api_key

# Sandbox Runner Microservice
SANDBOX_RUNNER_URL=http://sandbox-runner:8003
```

3. **Deploy Containers**:
```bash
docker compose up -d --build
```

4. **Verify Container Health**:
```bash
docker compose ps
docker compose logs -f
```

---

### 💻 Manual Bare-Metal Deployment (VPS / PM2)

To deploy directly on an Ubuntu/Debian VPS using PM2:

**Prerequisites**:
* Python 3.11+
* Docker Engine (running on the host for code execution)
* Node.js & PM2 (`npm install -g pm2`)
* Supabase project with `pgvector` enabled

#### 1. Setup Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 2. Pre-Pull Sandbox Execution Images
```bash
docker pull python:3.11-slim
docker pull node:18-alpine
docker pull alpine:latest
```

#### 3. Database Migration
Open your Supabase Project SQL Editor and execute the schema and migration scripts in `backend/memory/schema.sql`:
* Base tables & indexes (M1)
* Extended reasoning columns (M2)
* Semantic vector memory columns & `match_user_memories` RPC (M3)
* Channel profile inheritance (M4)
* Auto-code test mode column `auto_code_test_mode` (M5)
* Observability and cost columns in `request_logs` (M6)

#### 4. Launch Services under PM2
```bash
pm2 start infra/pm2.config.js
pm2 save
```

Verify service statuses:
```bash
pm2 status
curl http://127.0.0.1:8002/health
```

---

## 🔄 v4.0.0 Migration Guide & Safe Rollout Sequence

Upgrading from Zauq v3.x to v4.0.0 is fully backward-compatible with existing channel configurations. Follow these steps to ensure a seamless upgrade:

### Step 1: Environment Updates
Add the new v4 configuration keys to your `.env` file (refer to `.env.example`):
1. Add `SERPER_API_KEY` for Google web search grounding.
2. Configure your preferred Tier-1 provider keys (`ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`).
3. Set `AGENT_RUNTIME_ENABLED=false` and `MCP_ENABLED=false` initially.

### Step 2: Database Migration
Execute migrations M5 and M6 from `backend/memory/schema.sql` in your Supabase SQL Editor:
```sql
-- Migration M5: Auto Code Testing column
ALTER TABLE channel_profiles ADD COLUMN IF NOT EXISTS auto_code_test_mode BOOLEAN DEFAULT FALSE;

-- Migration M6: Observability and Cost Auditing
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS execution_mode TEXT DEFAULT 'standard';
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS tool_calls_count INTEGER DEFAULT 0;
ALTER TABLE request_logs ADD COLUMN IF NOT EXISTS total_cost_usd NUMERIC(10, 6) DEFAULT 0.0;
```

### Step 3: Dependency Installation
Install the updated package dependencies:
```bash
pip install -r requirements.txt
```

### Step 4: Safe Rollout Order

To guarantee maximum production stability, follow this staged rollout procedure:

```text
Development Testing (Local Pytest Suite)
       ↓
Private Discord Test Channel (Verify basic chat & commands)
       ↓
Enable Serper Search (/search and chat grounding)
       ↓
Enable Agent Runtime on Test Channel (/agent enable)
       ↓
Verify Sandbox Code Execution (/run and /sandbox auto_test:on)
       ↓
Enable MCP in Read-Only Mode (Inspect with /mcp list)
       ↓
Enable Sensitive MCP Tools with Human Approvals (/approve)
       ↓
General Community Server Rollout
```

---

## 🔒 Security, Isolation & Privacy

* **Docker Socket Isolation**: The backend web application has zero access to the host Docker daemon socket. Sandboxed execution requests travel exclusively through an isolated, authenticated HTTP microservice (`sandbox-runner`).
* **Air-Gapped Sandbox Containers**: User-submitted code executes in ephemeral containers with `--network none` (no internet connectivity), `--read-only` root filesystem, `--security-opt no-new-privileges`, 256MB RAM limits, and non-root execution (`nobody:nogroup`).
* **Constant-Time Internal Authentication**: Communications between the Discord Bot thin client, FastAPI Backend, and Sandbox Runner are secured with a shared `X-Zauq-Token` validated using constant-time `hmac.compare_digest()`.
* **DNS-Resolving SSRF Defense**: URL scrapers strictly resolve hostnames to IP addresses before initiating HTTP requests, blocking all loopback (`127.0.0.0/8`), RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local addresses, and cloud instance metadata endpoints (`169.254.169.254`).
* **Sliding-Window Rate Limiting**: Multi-tier request limiting protects against denial-of-service abuse (30 requests/min per guild, 10 requests/min per individual user).
* **Human-in-the-Loop Safeguards**: High-risk tool calls (e.g. database mutations, filesystem writes) pause execution and require explicit approval by an authorized administrator via Discord interactive buttons.
* **Privacy by Design**: Sensitive message content is never stored unencrypted. AI moderation logs store only SHA-256 cryptographic hashes. Users can execute `/forget` at any time to permanently purge all stored episodic memory vectors.

---

## 📋 v4.0.0 Release Changelog

| Feature | Details |
|---|---|
| 🔄 **Bounded Agent Runtime** | Multi-turn autonomous tool loop with deterministic step caps (default 4, max 8), loop cycle detection, and call deduplication |
| 🏛️ **Native Tier-1 Providers** | Direct first-class adapters for Claude 3.7 Sonnet / 3.5 Haiku, DeepSeek V3 / R1, and Qwen 2.5 / QwQ |
| 🌐 **Serper Search & Research v2** | High-performance Google search grounding via Serper.dev with parallel multi-source full-page reading via Jina Reader |
| 🐳 **Docker Socket Isolation** | Dedicated `sandbox-runner` microservice decoupling Docker daemon access from the web backend |
| 🧪 **Auto Code Testing Mode** | Optional `/sandbox auto_test:on` verifies generated code snippets in the sandbox before returning answers |
| 🔌 **Model Context Protocol (MCP)** | Standardized client supporting StdIO & SSE MCP tool servers with granular security policies |
| 🛡️ **Human-in-the-Loop Approvals** | Interactive Discord UI buttons (`Approve` / `Reject`) for dangerous or mutating agent tool actions |
| 📜 **31 Slash Commands** | Expanded slash command suite including `/agent`, `/mcp`, `/approve`, `/research`, and `/sandbox` |
| 📊 **Observability & Cost Tracking** | Step-by-step latency tracking, tool call counting, and per-query USD cost calculations in `request_logs` |

---

## 👤 Author & Maintainer

<table align="center">
  <tr>
    <td align="center">
      <img src="https://github.com/Muhammad-Hassan12.png" width="120px;" alt="Syed Muhammad Hassan"/><br />
      <sub><b>Syed Muhammad Hassan</b></sub><br />
      <sub>Founder & AI Architect @ AgenticEra Systems</sub><br /><br />
      <a href="https://github.com/Muhammad-Hassan12"><img src="https://img.shields.io/badge/GitHub-100000?style=for-the-badge&logo=github&logoColor=white"/></a>
      <a href="https://www.linkedin.com/in/syed-muhammad-hassan-aa112928b/"><img src="https://img.shields.io/badge/LinkedIn-0077B5?style=for-the-badge&logo=linkedin&logoColor=white"/></a>
    </td>
  </tr>
</table>

---

## 📄 License

This project is licensed under the **Apache License, Version 2.0** — see the [LICENSE](LICENSE) file for details.

*Built with ❤️ by Syed Muhammad Hassan for the global developer and Discord community.*
