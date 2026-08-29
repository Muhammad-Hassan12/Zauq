<div align="center">

<img src="assets/Zauq_Logo.png" alt="Zauq Logo" width="180px" style="border-radius: 20px; margin-bottom: 15px;" /><br />

# 🤖 Zauq (ذوق) — Next-Gen Hybrid AI Discord Companion

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Discord.py](https://img.shields.io/badge/Discord.py-2.3%2B-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io)
[![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Docker](https://img.shields.io/badge/Docker-Sandbox-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg?style=for-the-badge)](https://opensource.org/licenses/Apache-2.0)
[![Version](https://img.shields.io/badge/Version-3.2.5-FF6B6B?style=for-the-badge)](https://github.com/Muhammad-Hassan12/Zauq)

*A production-grade, state-of-the-art hybrid AI Discord bot architecture featuring explicit 3-Tier model routing, true vector-based semantic memory, Gemini extended thinking mode, universal multi-format document reading, sandboxed Docker code execution, free neural TTS voice synthesis, free AI image generation, XP/reputation gamification, AI content moderation, and interactive Discord UI mini-games.*

</div>

---

## 🌟 Overview

**Zauq (ذوق)** is an enterprise-ready, open-source AI Discord assistant built by **Syed Muhammad Hassan / AgenticEra Systems**. Designed around a decoupled, microservice-inspired architecture, Zauq separates Discord WebSocket event handling from AI reasoning.

It connects a lightweight `discord.py` gateway thin client to an ultra-fast **FastAPI backend engine** running locally under PM2 (configurable via `BACKEND_PORT` in `.env`).

Zauq supports multi-turn conversational memory with true vector-based semantic retrieval, automatic document text parsing (`.pdf`, `.docx`, `.xlsx`, `.txt`, `.py`, `.png`), sandboxed code execution inside isolated Docker containers, Gemini extended thinking mode, free neural text-to-speech with 19 voices across 8 languages, free AI image generation via Gemini, an XP/reputation leaderboard system, AI-powered content moderation, scheduled reminders, conversation export, and server lore RAG vector search.

---

## 📐 Architecture & Workflow

Zauq uses a decoupled architecture to guarantee 99.9% uptime, zero Gateway blocking, and effortless scalability:

```
                    ┌───────────────────────────────────────────┐
                    │            Discord Gateway (WS)           │
                    │  Voice Notes · Attachments · Slash Tree   │
                    └─────────────────────┬─────────────────────┘
                                          │
                         ┌────────────────▼────────────────┐
                         │     Zauq Bot (discord.py)       │
                         │   26 Commands · RBAC · XP       │
                         └────────────────┬────────────────┘
                                          │ HTTP (Port 8***)
                         ┌────────────────▼────────────────┐
                         │     FastAPI Backend Engine      │
                         │ Router · Memory · Media · Search│
                         └──────┬──────────┬───────────┬───┘
                                │          │           │
        ┌───────────────────────▼───┐   ┌───▼───────┐  └─────────────┐
        │   Supabase pgvector       │   │  Ollama   │   ┌────────────▼────────────┐
        │(L2 Semantic + L3 Lore RAG)│   │(Local VPS)│   │ Isolated Docker Sandbox │
        └───────────────────────────┘   └───────────┘   │ (Python, Node, Alpine)  │
                                                        └─────────────────────────┘
```

### Detailed Message Processing Sequence
1. **Event Capture**: The `discord.py` bot listens for user mentions, thread messages, attachments, or voice notes.
2. **XP Award**: Awards +1 XP to the user for message activity.
3. **AI Moderation Check**: If enabled, message is classified by AI content filter before processing.
4. **Context Window Assembly**: Fetches recent conversational context in the current thread/channel.
5. **Attachment Extraction**: Asynchronously downloads up to 4 attached files (`.pdf`, `.docx`, `.xlsx`, `.csv`, `.py`, `.png`, `.ogg`, `.mp3`) and packages them as base64 payloads.
6. **Backend Ingestion (`POST /api/chat`)**:
   - `file_parser` parses structured text and table data, extracts audio waveforms, or prepares images for Gemini Multimodal Vision.
   - `episodic.py` performs **semantic vector retrieval** of relevant L2 user facts (cosine similarity against the current query embedding), with graceful recency fallback.
   - `rag.py` retrieves L3 server lore via `match_server_lore` pgvector RPC.
   - Resolves operating mode and model via **Hierarchical Inheritance**: Channel Override $\to$ Community Server Default $\to$ System Fallback.
7. **Model Dispatch & Fallbacks**: Routes prompt through the active model tier. Automatically performs Gemini Flash Vision OCR and audio transcription fallbacks for text-only model tiers. **If a secondary provider fails, the user is notified via an orange embed after the response.**
8. **Single-Shot Delivery & Auto-Chunking**: Converts model response into clean Discord messages, delivers downloadable file attachments / ZIP archives, and auto-chunks text over 1,900 characters cleanly.

---

## 🛠️ Technology Stack & Infrastructure

| Layer / Category | Technologies & Tools | Description / Role |
|---|---|---|
| **Bot & Gateway Client** | `discord.py 2.3+`, `PyNaCl` | Async Discord WebSocket client, voice channels, 26 slash commands & UI buttons |
| **API Engine & Web Layer** | `FastAPI 0.100+`, `Uvicorn`, `httpx` | High-performance asynchronous REST & SSE backend engine on Port 8002 |
| **Multi-Tier AI Routing** | `Google Gemini 2.5 Flash/Pro`, `DO Gradient`, `Ollama`, `Kaggle T4` | 3-tier LLM execution with multimodal audio/vision fallbacks, thinking mode & Google search grounding |
| **Vector Memory & Storage** | `Supabase PostgreSQL`, `pgvector` (768-dim) | 3-layer memory: L1 working context, L2 true semantic vector memory, L3 server lore RAG |
| **Execution Sandboxing** | `Docker Engine` (`--network none`, read-only FS) | Ephemeral container sandbox for safe Python, JavaScript, and Bash execution |
| **Multimodal Document Parsers** | `pypdf`, `python-docx`, `openpyxl`, `Pillow` | Lossless document parsing, table extraction, and local meme rendering |
| **Neural Voice Synthesis** | `Microsoft Edge Neural TTS (edge-tts)` | Free cloud neural voice synthesis across 19 voices and 7 global languages |
| **Security & Cryptography** | `HMAC`, `ipaddress`, `socket`, `hashlib` | Constant-time authentication, DNS-resolving SSRF defense, SHA-256 moderation logs |
| **Process Supervision** | `PM2 Ecosystem`, `Python venv` | Background daemon supervision, reboot recovery, and automated log rotation |

---

## 🚀 Key Features

### 🏛️ 1. Hierarchical Configuration & Community Defaults (`scope: "server"` vs `scope: "channel"`)
* **Community Server Defaults**: Set permanent baseline model tier, provider, and mode across the entire Discord server.
* **Channel-Specific Overrides**: Lock dedicated channels (e.g. `#dev-chat` to Dev Mode + `gemini-2.5-pro` with code execution, or `#bot-lab` to Ollama) while the rest of the server uses community defaults.
* **Smart Reset (`/model reset`, `/mode_reset`)**: Easily clear channel overrides to revert back to community server inheritance.

### 🛡️ 2. Role-Based Access Control (RBAC) & Upper-Role Delegation (`/admin set_role`)
* **Administrator Protection**: Restricts model and operating mode configuration strictly to Server Administrators and members with `Manage Server` permissions.
* **Upper-Role Authorization (`/admin set_role`)**: Allows server owners to designate a custom moderator/staff role (e.g. `@AI-Admin` or `@Moderator`) with management privileges.
* **Security Rejection**: Unauthorized users receive a clean security rejection embed.

### 🎭 3. Dual Operating Modes (`/mode`)
Channels operate in per-channel modes saved to Supabase `channel_profiles`:
* **Dev Mode (`dev`)**: Technical persona (Senior Architect), low temperature (`0.2`), concise code snippets, and enabled sandboxed code execution (`/run`).
* **Hangout Mode (`hangout`)**: Casual persona, high temperature (`0.75`), server lore recall, meme rendering, voice TTS, voice-to-voice replies, and trivia mini-games.

### ⚡ 4. 3-Tier Explicit Model Router & Clean Provider Taxonomy
Zauq rejects unreliable cascade fallbacks in favor of **explicit locking**. Channels stay locked to the chosen model provider:
* **Tier 1 (Cloud Primary)**:
  * **Google AI Studio (`gemini` / `google`)**: `gemini-2.5-flash` (Default), `gemini-2.5-pro`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3-pro-preview`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it` + Google Search Grounding.
  * **DigitalOcean Gradient (`digitalocean`)**: `kimi-k3`, `kimi-k2.6`, `kimi-k2.5`, `glm-5.3`, `glm-5.2`, `glm-5.1`, `glm-5`, `deepseek-v4-pro`, `deepseek-4-flash`, `deepseek-3.2`, `qwen3.8-max`, `qwen3.5-397b-a17b`, `llama-4-maverick`, `llama3.3-70b-instruct`, `minimax-m2.5`, `nemotron-3-ultra-550b`.
* **Tier 2 (Local VPS)**: Local Ollama server (`ollama`: `qwen3.5:4b` - zero API cost).
* **Tier 3 (Batch GPU)**: Cloudflared tunneled Kaggle T4 worker (`kaggle`: `qwen3.5-t4` - pings `/health` before locking).

> **⚠️ Transparent Fallback Alerts**: When a configured provider (DigitalOcean, Ollama, Kaggle) fails and Gemini Flash is substituted, Zauq sends a visible **orange embed notification** after the response so users always know what model served them.

### 🧠 5. `/thinking` — Universal Extended Reasoning & Thinking Mode *(v3.2.5 New)*
Toggle deep extended-thinking reasoning per channel across **all model providers**:
* **Gemini Models**: Allocates up to **16,384 dedicated thinking tokens** via native `thinkingConfig` API budget.
* **DigitalOcean (Kimi, GLM, DeepSeek, Qwen), Ollama & Kaggle**: Injects Deep Chain-of-Thought (CoT) multi-phase reasoning directives with expanded token allowances (up to 32k tokens).
* **Zero Leakage**: Internal `<thought>` and `<think>` scratchpad blocks are automatically sanitized so internal thinking never leaks to chat.
* **Command**: `/thinking mode:on` (admin only, per-channel scope).
* **Output tokens**: up to **65,536 tokens** giving models full room to generate comprehensive, un-truncated answers.

### 📄 6. Universal Document, Vision & Voice Note Ingestion (30,000 Token Capacity)
Upload any document, code file, image, or voice note directly to Discord! Zauq's parsing engine supports up to **120,000 characters (~30,000 tokens / ~3,000+ lines of text)** per document:
* **Multilingual Voice Notes**: `.ogg`, `.mp3`, `.wav`, `.m4a`, `.opus` (Native Gemini 2.5 Flash audio waveform ingestion for **Urdu (اردو)**, **Roman Urdu**, **Hindi**, **Arabic**, **English**, etc. with zero latency + automated fallback transcriber for open models)
* **Code & Text Files**: `.txt`, `.py`, `.js`, `.ts`, `.html`, `.css`, `.json`, `.yaml`, `.md`, `.log`, `.sql`, `.sh` (Parsed in full up to 30,000 tokens)
* **PDF Documents**: `.pdf` (text extracted page-by-page via `pypdf` with 120k char limits)
* **Word Documents**: `.docx` (text and tables extracted via `python-docx`)
* **Spreadsheets & Data**: `.csv`, `.xlsx` (parsed via `openpyxl` into structured Markdown tables)
* **Multimodal Vision & OCR Fallback**: `.png`, `.jpg`, `.jpeg`, `.webp` (sent natively to Gemini Vision or transcribed for text models)

### 📁 7. On-Demand Dynamic File Generation & Project ZIP Bundles
* **On-Demand File Delivery**: Generates complete, un-truncated `.py`, `.html`, `.json`, `.sql`, `.md`, `.sh`, `.css` files on user demand (up to **65,536 output tokens** — full Gemini capacity).
* **Dual Output Architecture**: Displays an interactive syntax-highlighted code preview directly in chat **and attaches the standalone file as a native Discord attachment (`discord.File`)**.
* **Automatic Project ZIP Bundling**: When 2 or more files are created simultaneously (e.g. full frontend + backend), Zauq automatically packages them into a `project_files.zip` downloadable archive.

### 🌐 8. Deep Web Roaming, Autonomous Search & URL Scraper (`/search`)
* **Autonomous Deep Web Roaming**: Concurrently visits and scrapes the **full readable content of the top 2–3 search result pages** in parallel via `asyncio.gather()` and Jina Reader / SSRF-safe parsers, injecting authoritative multi-source context rather than brief 20-word snippets.
* **Smart Multi-Query Expansion**: NLP optimizer strips conversational filler and decomposes complex queries into 2–3 targeted search queries to maximize factual accuracy.
* **Domain & Category Filters**: Target searches directly to **💻 GitHub Repos (`github`)**, **📑 ArXiv Papers (`arxiv`)**, **📚 Developer Docs (`docs`)**, **📖 Wikipedia (`wikipedia`)**, or **📰 News (`news`)**.
* **Automatic Chat Intent Triggering**: Live search activates **automatically during normal chat** whenever the user asks for research, real-time events, news, or factual lookups without requiring a slash command.
* **Google Search Grounding**: Gemini models dynamically roam Google Search in real-time and format clickable markdown citation links.
* **Live URL Content Reader**: Drop any HTTP/HTTPS link in chat (e.g. documentation, arXiv papers, news articles) and Zauq will automatically fetch and read the webpage content.

### 🧠 9. True 3-Layer Semantic Vector Memory Architecture *(v3.2.5 Powerfix)*
* **L1 Working Memory**: 8-message thread context window with intelligent message chunking.
* **L2 User Episodic Memory (`user_memories`)** — fully vector-based:
  * **Embedding generation** on every extracted fact (768-dim `gemini-embedding-001` vectors — stored, not null)
  * **Semantic retrieval** via `match_user_memories` pgvector RPC — ranked by `similarity × importance_score` against the current user query, not just recency
  * **Deduplication** at cosine similarity ≥ 0.92 (near-duplicates skipped, existing fact reinforced)
  * **Contradiction detection** — negation-signal facts (e.g. *"stopped using X"*) halve the importance of contradicted memories and are tagged as corrections
  * **Importance scoring** — LLM-assigned importance (0–1) per fact, boosted for personal/technical categories
  * **Access reinforcement** — retrieved memories gain `access_count++` and a refreshed `last_accessed_at`
  * **Memory decay** — a 24h background worker reduces importance of unaccessed memories by 5%/cycle and prunes facts below 0.15 importance threshold
* **L3 Server Lore RAG (`server_lore`)**: Supabase `match_server_lore` pgvector similarity search grounds answers in server rules, inside jokes, and ingested GitHub READMEs.

### ⚙️ 10. Unified Multi-Input Sandboxed Code Execution (`/run`, Apps ➔ Run Code)
Run Python 3, Node.js, or Bash code safely in ephemeral, isolated Docker containers with 4 flexible input methods:
* **🪟 Interactive Multiline Modal Editor**: Run `/run` without arguments to pop up a full-screen paragraph editor with Enter-key newlines, indentation, and paste support (up to 4,000 characters).
* **📁 Script File Attachment (`/run file:script.py`)**: Drag-and-drop `.py`, `.js`, or `.sh` script files directly to execute complete programs up to 50KB.
* **⚡ Inline Quick-Run (`/run code:print(...)`)**: Instant single-line execution for fast math and one-liners.
* **🖱️ Message Context Menu (`Apps ➔ Run Code Snippet`)**: Right-click any Discord message containing a ```python ... ``` code block to test-run it in Docker with 1 click.
* **Security Constraints**: `--network none` (no internet access), `--memory 256m`, `--cpus 0.5`, `--pids-limit 50`, `--read-only`, 5.0s execution timeout. Gated to `dev` mode or channels with `allow_code_exec = true`.

### 🔊 11. Free Multi-Language Neural TTS & Voice Companion (`/tts`, `/voice`)
* **Engine**: Microsoft Edge Neural TTS (`edge-tts`). Zero API cost.
* **19 Voices** across **8 Languages**: English (US/UK), Urdu, Hindi, Arabic, Spanish, French, German, Japanese.
* **Voice Channel Support**: `/voice join` connects Zauq to voice channels for audio playback.
* **Voice-to-Voice Companion**: Automatically generates voice note audio responses when voice notes are sent in Hangout mode.

### 🖼️ 12. Free AI Image Generation & Local Meme Rendering (`/image`, `/meme`)
* **AI Image Generation (`/image`)**: Primary engine is **Gemini Flash Image** (`gemini-3.1-flash-image`) — **completely free** via existing Gemini API key. Secondary options: DigitalOcean Gradient (`stable-diffusion-3.5-large` & `ideogram-3.0-turbo`).
* **Local Meme Renderer (`/meme`)**: Local Pillow canvas rendering top/bottom Impact text with outlines.

### 🏆 13. XP & Reputation Leaderboard System
* **Automated XP**: +1 XP per message, +2 per command, +5 per correct trivia answer.
* **Leveling Formula**: `Level = floor(sqrt(XP / 100)) + 1`.
* **Commands**: `/rank` (personal stats), `/leaderboard` (top 10 server members).

### 🛡️ 14. AI Content Moderation
* **AI-Powered**: Uses the active AI model to classify messages as `safe`, `borderline`, or `toxic`.
* **Auto-Actions**: Toxic messages auto-deleted with DM warning; borderline logged for admin review.
* **Configurable**: `/moderation enable`, `/moderation sensitivity`, `/moderation log`.

### 🎮 15. Interactive Mini-Games, Reminders & Utilities
* **Interactive Trivia (`/trivia`)**: Difficulty-tiered mini-game with Discord UI buttons, XP rewards, and server lore questions.
* **Scheduled Reminders (`/remind`)**: Set reminders from 1 minute to 7 days with automatic delivery.
* **Conversation Export (`/export`)**: Export thread history as Markdown files.
* **Thread Summarization (`/summarize`)**: AI-powered bullet-point summaries of discussions.
* **Privacy & Data Control (`/forget`, `/privacy`)**: GDPR-compliant `/forget` command purges all stored user vector data.
* **Direct Server Sync (`!sync`)**: Forces instant slash command registration to your server.

---

## 📜 Complete Slash Command Reference (27 Command Groups · 35 Actions)

| Command | Category | Description |
|---|---|---|
| `/info` | Core | View complete live specifications, active model tier, mode, and engine parameters. |
| `/mode` | Core | Switch channel or server operating mode (`dev` or `hangout`). |
| `/mode_reset` | Core | Clear channel mode override and revert to community default. |
| `/summarize` | Core | Summarize thread or channel discussion into bullet points. |
| `/thinking` | Core | Toggle Gemini deep-thinking/reasoning mode for a channel (admin only). |
| `/search` | Search | Deep web roaming search with full-page reading, deep toggle & category filters. |
| `/file generate` | File | Generate a complete code or document file on demand. |
| `/create_file` | File | Quick shortcut to generate a downloadable code or document file. |
| `/model status` | Models | View active model tier, provider, model name, and inheritance scope. |
| `/model set` | Models | Set model tier/provider (channel-specific or permanent community default). |
| `/model reset` | Models | Clear channel model override and revert to community server default. |
| `/run` | Sandbox | Safely execute Python, JS, or Bash code in Docker. |
| `/remember` | Lore | Save a server lore fact or rule into vector memory. |
| `/rank` | XP | Check your XP level, rank, and progress. |
| `/leaderboard` | XP | View top server members by XP. |
| `/remind` | Utility | Schedule a reminder message (1 min to 7 days). |
| `/export` | Utility | Export conversation history as a Markdown file. |
| `/github pr` | GitHub | Fetch and summarize a GitHub Pull Request diff. |
| `/github issue` | GitHub | Fetch and display a GitHub Issue description. |
| `/ingest_repo` | GitHub | Ingest a GitHub repository README into server lore. |
| `/tts` | Voice | Generate high-quality multi-language neural speech. |
| `/voice join` | Voice | Connect Zauq to your voice channel. |
| `/voice leave` | Voice | Disconnect Zauq from the voice channel. |
| `/meme` | Media | Generate text-overlay memes with impact font styling. |
| `/image` | Media | Generate AI art (Gemini Flash Image free / DigitalOcean). |
| `/trivia` | Games | Play interactive trivia with difficulty choices & XP rewards. |
| `/moderation enable` | Admin | Enable or disable AI content moderation. |
| `/moderation sensitivity` | Admin | Set AI content filtering sensitivity level. |
| `/moderation log` | Admin | View recent moderation log entries. |
| `/admin set_role` | Admin | Designate an upper role with management permissions for Zauq. |
| `/admin memory` | Admin | View vector memory and API usage statistics. |
| `/admin channels` | Admin | View channels with configured AI profiles. |
| `/stats` | Analytics | View server volume, latency, and provider metrics. |
| `/forget` | Privacy | Purge stored episodic memories for your User ID. |
| `/privacy` | Privacy | Display Zauq data privacy disclosure. |
| `!sync` | Admin | Force instant slash command sync to your Discord server. |

---

## 📂 Code Base Structure

```
Zauq/
├── backend/
│   ├── config.py                 # Pydantic Settings & Environment Loader
│   ├── main.py                   # FastAPI Application Entrypoint (Port 8002)
│   ├── logging_config.py         # Centralized Structured Logging Configuration
│   ├── games/
│   │   └── trivia.py             # Server Lore Dynamic Trivia Engine
│   ├── integrations/
│   │   ├── github_client.py      # GitHub PR, Issue & Repo Ingestion Client
│   │   └── web_search.py         # SSRF-Protected Live Web Search, Jina Scraper & Citations
│   ├── media/
│   │   ├── gemini_image.py       # Gemini Native Image Generation Client (Free)
│   │   ├── meme_generator.py     # Pillow Text-Overlay Image Renderer
│   │   └── tts.py                # Edge-TTS Multi-Language Neural Voice Synthesizer (19 Voices)
│   ├── memory/
│   │   ├── db.py                 # Async Supabase Client — vector search, decay, thinking toggle
│   │   ├── embeddings.py         # Gemini 768-dim Vector Embeddings (gemini-embedding-001)
│   │   ├── episodic.py           # True Vector Memory: extract, embed, dedup, contradiction, decay
│   │   ├── memory_worker.py      # 24h Background Memory Decay & Expiry Worker (v3.2.5 New)
│   │   ├── metrics.py            # Latency & Token Metric Auditing
│   │   ├── rag.py                # Vector Similarity RAG Search (match_server_lore RPC)
│   │   ├── xp.py                 # XP & Reputation System Logic
│   │   └── schema.sql            # Supabase pgvector Schema (9 Tables + match_user_memories RPC)
│   ├── middleware/
│   │   ├── auth_middleware.py    # Constant-Time Internal API Key Header Authentication
│   │   └── rate_limiter.py       # Sliding-Window Rate Limiting (Guild, User, IP)
│   ├── models/
│   │   ├── gemini_client.py      # Gemini Adapter — thinking mode + 65,536 token output (v3.2.5)
│   │   ├── kaggle_client.py      # Tunneled Kaggle GPU Worker Adapter
│   │   ├── openai_compatible_client.py # DigitalOcean & Ollama Adapter
│   │   └── router.py             # 3-Tier Explicit Model Router + Multimodal Fallbacks
│   ├── moderation/
│   │   └── content_filter.py     # AI Content Classification (safe/borderline/toxic)
│   ├── parsers/
│   │   ├── audio_transcriber.py  # Multilingual Audio Transcriber (Urdu/Hindi/Arabic/English)
│   │   └── file_parser.py        # PDF, DOCX, XLSX, Vision, Audio & <zauq_file> Parser
│   ├── routers/
│   │   ├── admin.py              # Metrics, Memory Stats, XP Leaderboard & Purge Endpoints
│   │   ├── chat.py               # Chat Engine — personas, semantic memory, thinking, fallback alerts
│   │   ├── context.py            # Semantic Context Ranking Endpoint
│   │   ├── games.py              # Trivia Game Generator Endpoint
│   │   ├── github.py             # GitHub API Integration Endpoints
│   │   ├── lore.py               # Server Lore Vector CRUD Endpoints
│   │   ├── media.py              # TTS, Meme & AI Image Endpoints (Gemini + DO)
│   │   ├── model.py              # Model Status, Autocomplete & Set Endpoints
│   │   ├── moderation.py         # AI Moderation Check, Log & Settings Endpoints
│   │   ├── reminders.py          # Reminder CRUD & Delivery Endpoints
│   │   ├── sandbox.py            # Ephemeral Docker Code Execution Router (Bounded Timeouts)
│   │   └── xp_router.py          # XP Award & Leaderboard Endpoints
│   ├── sandbox/
│   │   └── code_runner.py        # Docker Container Subprocess Sandbox (--network none)
│   └── utils/
│       ├── __init__.py           # Package Initializer
│       ├── temp_manager.py       # Temp File Lifecycle Manager (Auto-Cleanup Worker)
│       ├── test_community_config.py # Server/Channel Scope & RBAC Test Suite
│       ├── test_deep_search.py   # Deep Roaming & Multi-Query Search Test Suite
│       ├── test_info_command.py  # System Specifications /info Endpoint Test Suite
│       ├── test_new_features.py  # Feature Validation Test Suite
│       ├── test_reply_ingestion.py # Replied Reference Ingestion Test Suite
│       ├── test_sandbox_suite.py # Multi-Input Sandbox & Context Menu Test Suite
│       └── test_security_hardening.py # SSRF, Input Bounds & Auth Security Test Suite
├── bot/
│   ├── api.py                    # Centralized Bot Backend API Client & Auth Headers
│   ├── auth.py                   # Discord Permission & Upper-Role RBAC Verifier
│   ├── client.py                 # Discord.py Gateway Bot — replies, fallback alerts, voice ingestion
│   ├── stream_buffer.py          # Intelligent Multi-Message Chunking (>1900 chars)
│   ├── commands/
│   │   ├── admin_slash.py        # /admin memory, /admin channels & /admin set_role Commands
│   │   ├── exec_slash.py         # /run Sandbox Command
│   │   ├── export_slash.py       # /export Conversation Export Command
│   │   ├── file_slash.py         # /file generate & /create_file Commands
│   │   ├── github_slash.py       # /github pr, /github issue & /ingest_repo Commands
│   │   ├── image_slash.py        # /image AI Art Command (Gemini + DO)
│   │   ├── info_slash.py         # /info System Specifications & Active Config Command
│   │   ├── meme_slash.py         # /meme Local Meme Renderer Command
│   │   ├── model_slash.py        # /model status, /model set & /model reset Commands
│   │   ├── moderation_slash.py   # /moderation enable, sensitivity & log Commands
│   │   ├── privacy_slash.py      # /forget & /privacy Commands
│   │   ├── remember_slash.py     # /remember Server Lore Command
│   │   ├── remind_slash.py       # /remind Scheduled Reminder Command
│   │   ├── search_slash.py       # /search Web Search Command
│   │   ├── stats_slash.py        # /stats Analytics Command
│   │   ├── summarize_slash.py    # /summarize Thread Summary Command
│   │   ├── thinking_slash.py     # /thinking Toggle Gemini Reasoning Mode (v3.2.5 New)
│   │   ├── trivia_slash.py       # /trivia Interactive Quiz Command
│   │   ├── voice_slash.py        # /tts & /voice Commands
│   │   └── xp_slash.py           # /rank & /leaderboard Commands
│   └── plugins/
│       └── __init__.py           # Auto-Discovery Plugin Loader
├── assets/
│   └── Zauq_Logo.png             # Official Zauq Branding & Logo Asset
├── infra/
│   └── pm2.config.js             # PM2 Production Ecosystem File (PYTHONPATH)
├── .github/
│   ├── workflows/ci.yml          # GitHub Actions Automated CI/CD Test Pipeline
│   └── ISSUE_TEMPLATE/           # Standard Bug Report & Feature Request Templates
├── .env.example                  # Environment Configuration Template
├── requirements.txt              # Python Package Dependencies
├── docker-compose.yml            # 1-Click Multi-Container Deployment Orchestration
├── Dockerfile.backend            # Container Image for FastAPI Backend + Docker CLI
├── Dockerfile.bot                # Container Image for Discord Bot
├── USER_GUIDE.md                 # Complete User Manual (v3.2.5)
├── DEPLOYMENT.md                 # Deployment & Infrastructure Guide
├── CONTRIBUTING.md               # Community Contribution & Testing Guidelines
├── PRIVACY.md                    # Privacy Policy Document
├── NOTICE.md                     # Trademark, Branding & Third-Party Terms Notice
├── LICENSE                       # Apache License 2.0
└── README.md                     # Open-Source Project Documentation (v3.2.5)
```

---

## 🔧 Installation & Deployment

### 🐳 1-Click Docker Deployment (Recommended)

The easiest way to self-host Zauq is using Docker Compose. This automatically spins up the FastAPI backend, the Discord Bot, and handles all network and sandbox permissions.

1. **Clone and Configure**:
```bash
git clone https://github.com/Muhammad-Hassan12/Zauq.git
cd Zauq
cp .env.example .env
nano .env # Fill in your tokens
```

2. **Run with Docker Compose**:
```bash
docker-compose up -d --build
```

### 💻 Manual Bare-Metal Deployment

If you prefer to run Zauq directly on your host machine (e.g. Ubuntu VPS) using PM2.

**Prerequisites**:
* **Python**: 3.11 or higher
* **Docker Engine**: Installed and running on host (Required for the Code Execution Sandbox)
* **PM2**: Node.js process manager installed globally (`npm install -g pm2`)
* **Supabase Account**: With `pgvector` extension enabled

#### 1. Clone Repository & Environment Setup
```bash
git clone https://github.com/Muhammad-Hassan12/Zauq.git
cd Zauq

cp .env.example .env
nano .env
```

Fill in your environment credentials:
```env
DISCORD_BOT_TOKEN=your_discord_bot_token
GEMINI_API_KEY=your_google_ai_studio_key
DO_MODEL_ACCESS_KEY=your_digitalocean_gradient_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_service_role_key
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8002
INTERNAL_API_KEY=your_random_64_char_hex_secret_here
```

### 2. Create Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Pre-Pull Docker Execution Images
```bash
docker pull python:3.11-slim
docker pull node:18-alpine
docker pull alpine:latest
```

### 4. Database Initialization
Run the SQL in `backend/memory/schema.sql` inside your Supabase SQL Editor to initialize all 9 tables and the RPC functions. The schema includes:
- All base tables: `channel_profiles`, `model_selection`, `guild_configs`, `user_memories`, `server_lore`, `request_logs`, `user_stats`, `scheduled_reminders`, `moderation_log`
- `match_server_lore` RPC for L3 lore retrieval
- `match_user_memories` RPC for true L2 semantic retrieval (v3.2.5)
- All required indexes including vector indexes and decay query indexes (v3.2.5)
- v3.2.5 column additions: `channel_profiles.thinking_enabled`, `user_memories.importance_score`, `user_memories.last_accessed_at`, `user_memories.access_count`

### 5. Launch Services with PM2
```bash
pm2 start infra/pm2.config.js
pm2 save
```

Verify service health:
```bash
pm2 status
pm2 logs zauq-backend
pm2 logs zauq-bot
curl http://127.0.0.1:8002/health
```

---

## 🔒 Security & Privacy

* **Constant-Time Internal Authentication**: Shared `X-Zauq-Token` secret validation using `hmac.compare_digest()` protects backend endpoints against timing attacks and unauthorized network access.
* **SSRF-Protected Web Scraping**: URL fetching strictly enforces DNS resolution and IP verification, blocking loopback (`127.0.0.0/8`), private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and cloud metadata (`169.254.169.254`).
* **Multi-Tier Rate Limiting**: Sliding-window rate limit enforces **30 req/min per guild** and **10 req/min per user** to prevent API abuse. Request body properly cached to prevent body consumption bugs.
* **Strict Sandbox Isolation**: Executed code runs inside non-root Docker containers (`nobody` user `65534:65534`) with zero network access (`--network none`), `--read-only` rootfs, `--security-opt no-new-privileges`, 256MB RAM caps, and bounded timeouts.
* **Row-Level Security (RLS)**: Supabase PostgreSQL tables enforce strict Row-Level Security policies, restricting programmatic access exclusively to the backend service role.
* **Privacy-Preserving Moderation Logs**: Toxic content is never stored in plaintext; only a SHA-256 cryptographic hash (`[hash:{content_hash}]`) is logged for verification.
* **Structured Logging & Safety**: All components use Python `logging` with centralized rotation in `logs/zauq.log`. Sensitive HTTP query parameters and secrets are suppressed from logs.
* **Data Guarantee & Right to be Forgotten**: User messages are processed in real-time and **never stored or used for model training**. Users can run `/forget` at any time to permanently purge their stored episodic memory.

---

## 📋 v3.2.5 Changelog

| Feature | Details |
|---|---|
| 🧠 **Thinking Mode** | `/thinking` slash command toggles Gemini extended reasoning (16,384 thinking tokens) per channel |
| 📈 **65,536 Output Tokens** | Raised from 8,192 — full Gemini 2.5 capacity for long-form generation |
| 🔬 **True Vector L2 Memory** | Embeddings now generated & stored on every fact; semantic retrieval via `match_user_memories` RPC; cosine dedup, contradiction detection, importance scoring, 24h decay worker |
| ⚠️ **Fallback Notifications** | Orange embed alert sent to users when their configured provider falls back to Gemini Flash |

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
