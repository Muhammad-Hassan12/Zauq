<div align="center">

# 🤖 Zauq (ذوق) — Next-Gen Hybrid AI Discord Companion

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Discord.py](https://img.shields.io/badge/Discord.py-2.3%2B-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io)
[![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white)](https://supabase.com)
[![Docker](https://img.shields.io/badge/Docker-Sandbox-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://docker.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

*A production-grade, state-of-the-art hybrid AI Discord bot architecture featuring explicit 3-Tier model routing, 3-Layer pgvector memory, universal multi-format document reading, sandboxed Docker code execution, free neural TTS voice synthesis, free AI image generation, XP/reputation gamification, AI content moderation, and interactive Discord UI mini-games.*

</div>

---

## 🌟 Overview

**Zauq (ذوق)** is an enterprise-ready, open-source AI Discord assistant built by **Syed Muhammad Hassan / AgenticEra Systems**. Designed around a decoupled, microservice-inspired architecture, Zauq separates Discord WebSocket event handling from AI reasoning. 

It connects a lightweight `discord.py` gateway thin client to an ultra-fast **FastAPI backend engine** running locally under PM2 on Port **8002**.

Zauq supports multi-turn conversational memory, automatic document text parsing (`.pdf`, `.docx`, `.xlsx`, `.txt`, `.py`, `.png`), sandboxed code execution inside isolated Docker containers, free neural text-to-speech in 10+ languages, free AI image generation via Gemini, an XP/reputation leaderboard system, AI-powered content moderation, scheduled reminders, conversation export, and server lore RAG vector search.

---

## 📐 Architecture & Workflow

Zauq uses a decoupled architecture to guarantee 99.9% uptime, zero Gateway blocking, and effortless scalability:

```
                    ┌───────────────────────────────────────────┐
                    │            Discord Gateway (WS)           │
                    └─────────────────────┬─────────────────────┘
                                          │
                         ┌────────────────▼────────────────┐
                         │     Zauq Bot (discord.py)       │
                         │  21 Commands · XP · Moderation  │
                         └────────────────┬────────────────┘
                                          │ HTTP (Port 8002)
                         ┌────────────────▼────────────────┐
                         │     FastAPI Backend Engine      │
                         │ Router · Memory · Media · Tasks │
                         └──────┬──────────┬──────────┬────┘
                                │          │          │
        ┌───────────────────────▼──┐   ┌───▼───────┐  └─────────────┐
        │   Supabase pgvector      │   │  Ollama   │   ┌────────────▼────────────┐
        │(L2 Facts & L3 Server Lore)│   │ (Local VPS)│   │ Isolated Docker Sandbox │
        └──────────────────────────┘   └───────────┘   │ (Python, Node, Alpine)  │
                                                       └─────────────────────────┘
```

### Detailed Message Processing Sequence
1. **Event Capture**: The `discord.py` bot listens for user mentions, thread messages, or attachments.
2. **XP Award**: Awards +1 XP to the user for message activity.
3. **AI Moderation Check**: If enabled, message is classified by AI content filter before processing.
4. **Context Window Assembly**: Fetches the last **15 messages** in the current thread/channel.
5. **Attachment Extraction**: Asynchronously downloads up to 3 attached files (`.pdf`, `.docx`, `.xlsx`, `.csv`, `.py`, `.log`, `.png`) and packages them as base64 payloads.
6. **Backend Ingestion (`POST /api/chat`)**:
   - `file_parser` parses structured text and table data or formats base64 images for Gemini Multimodal Vision.
   - `db_helper` retrieves L2 user facts (`user_memories`) and L3 server lore vector embeddings (`server_lore` pgvector RPC).
   - Assembles system persona based on the active operating mode (`dev` vs `hangout`).
7. **Model Dispatch**: Routes prompt through the explicitly locked channel model tier (Tier 1 Gemini/DO, Tier 2 Ollama, Tier 3 Kaggle).
8. **Single-Shot Delivery & Auto-Chunking**: Converts model response into clean Discord messages. If output > 1,900 characters, `split_message_chunks()` cleanly splits text at line breaks and code block boundaries (` ``` `) to preserve Markdown formatting.

---

## 🚀 Key Features

### 🎭 1. Dual Operating Modes (`/mode`)
Channels operate in per-channel modes saved to Supabase `channel_profiles`:
* **Dev Mode (`dev`)**: Technical persona (Senior Architect), low temperature (`0.2`), concise code snippets, and enabled sandboxed code execution (`/run`).
* **Hangout Mode (`hangout`)**: Casual persona, high temperature (`0.75`), server lore recall, meme rendering, voice TTS, and trivia mini-games.

### ⚡ 2. 3-Tier Explicit Model Router
Zauq rejects unreliable cascade fallbacks in favor of **explicit channel locking**. Channels stay locked to the chosen model provider:
* **Tier 1 (Cloud Primary)**:
  * **Google AI Studio (Gemini & Gemma Families)**: `gemini-2.5-flash` (Default), `gemini-2.5-pro`, `gemini-3.6-flash`, `gemini-3.5-flash`, `gemini-3-pro-preview`, `gemma-4-26b-a4b-it`, `gemma-4-31b-it`.
  * **DigitalOcean Gradient Serverless**: `kimi-k3`, `glm-5.1`, `glm-5.2`, `deepseek-v4-pro`, `deepseek-4-flash`, `qwen3.5-397b-a17b`, `llama3.3-70b-instruct`.
* **Tier 2 (Local VPS)**: Local Ollama server (`qwen3.5:4b` - zero API cost).
* **Tier 3 (Batch GPU)**: Cloudflared tunneled Kaggle T4 worker (`qwen3.5-t4` - pings `/health` before locking).

### 📄 3. Universal Document & File Ingestion
Upload any document or code file directly to Discord! Zauq automatically parses:
* **Code & Text**: `.txt`, `.py`, `.js`, `.ts`, `.html`, `.css`, `.json`, `.yaml`, `.md`, `.log`, `.sql`, `.sh`
* **PDF Documents**: `.pdf` (text extracted page-by-page via `pypdf`)
* **Word Documents**: `.docx` (text and tables extracted via `python-docx`)
* **Spreadsheets & Data**: `.csv`, `.xlsx` (parsed via `openpyxl` into structured Markdown tables)
* **Multimodal Vision**: `.png`, `.jpg`, `.jpeg`, `.webp` (sent natively to Gemini Vision API to analyze screenshots, stack traces, and diagrams)

### 🧠 4. 3-Layer Vector Memory Architecture
* **L1 Working Memory**: 15-message thread context window.
* **L2 User Episodic Memory (`user_memories`)**: Background worker extracts user facts after every message, storing 768-dim embeddings via `gemini-embedding-001`.
* **L3 Server Lore RAG (`server_lore`)**: Supabase `match_server_lore` pgvector similarity search grounds answers in server rules, inside jokes, and ingested GitHub READMEs.

### ⚙️ 5. Sandboxed Code Execution (`/run`)
Run Python, Node.js, or Bash code safely in ephemeral Docker containers:
* **Security Constraints**: `--network none` (no internet access), `--memory 256m`, `--cpus 0.5`, 5.0 second execution timeout.
* **Gated Access**: Restricted to `dev` mode or channels with `allow_code_exec = true`.

### 🔊 6. Free Multi-Language Neural TTS & Voice Companion (`/tts`, `/voice`)
* **Engine**: Microsoft Edge Neural TTS (`edge-tts`). Zero API cost.
* **19 Voices** across **7 Languages**: English (US/UK), Urdu, Hindi, Arabic, Spanish, French, German, Japanese.
* **Voice Channel Support**: `/voice join` connects Zauq to voice channels for audio playback.

### 🖼️ 7. Free AI Image Generation & Local Meme Rendering (`/image`, `/meme`)
* **AI Image Generation (`/image`)**: Primary engine is **Gemini Flash Image** (`gemini-3.1-flash-image`) — **completely free** via existing Gemini API key. Secondary options: DigitalOcean Gradient (`stable-diffusion-3.5-large` & `ideogram-3.0-turbo`).
* **Local Meme Renderer (`/meme`)**: Local Pillow canvas rendering top/bottom Impact text with outlines.

### 🏆 8. XP & Reputation Leaderboard System
* **Automated XP**: +1 XP per message, +2 per command, +5 per correct trivia answer.
* **Leveling Formula**: `Level = floor(sqrt(XP / 100)) + 1`.
* **Commands**: `/rank` (personal stats), `/leaderboard` (top 10 server members).

### 🛡️ 9. AI Content Moderation
* **AI-Powered**: Uses the active AI model to classify messages as `safe`, `borderline`, or `toxic`.
* **Auto-Actions**: Toxic messages auto-deleted with DM warning; borderline logged for admin review.
* **Configurable**: `/moderation enable`, `/moderation sensitivity`, `/moderation log`.

### 🎮 10. Interactive Mini-Games, Reminders & Utilities
* **Interactive Trivia (`/trivia`)**: Difficulty-tiered mini-game with Discord UI buttons, XP rewards, and server lore questions.
* **Scheduled Reminders (`/remind`)**: Set reminders from 1 minute to 7 days with automatic delivery.
* **Conversation Export (`/export`)**: Export thread history as Markdown files.
* **Thread Summarization (`/summarize`)**: AI-powered bullet-point summaries of discussions.
* **Privacy & Data Control (`/forget`, `/privacy`)**: GDPR-compliant `/forget` command purges all stored user vector data.

### 🔌 11. Plugin Extension System
* **Auto-Discovery**: Place any `.py` file with an `async def setup(bot)` in `bot/plugins/` — automatically loaded on startup.
* **Community-Ready**: Build custom slash commands as Discord cogs without modifying core code.

---

## 📜 Complete Slash Command Reference (21 Commands)

| Command | Category | Description |
|---|---|---|
| `/mode` | Core | Switch channel operating mode (`dev` or `hangout`). |
| `/summarize` | Core | Summarize thread or channel discussion into bullet points. |
| `/model status` | Models | View current model tier, provider, and model name. |
| `/model set` | Models | Set channel model tier (1, 2, 3), provider, and model name. |
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
| `/admin memory` | Admin | View vector memory and API usage statistics. |
| `/admin channels` | Admin | View channels with configured AI profiles. |
| `/stats` | Analytics | View server volume, latency, and provider metrics. |
| `/forget` | Privacy | Purge stored episodic memories for your User ID. |
| `/privacy` | Privacy | Display Zauq data privacy disclosure. |

---

## 📂 Code Base Structure

```
Zauq/
├── backend/
│   ├── config.py                 # Pydantic Settings & Environment Loader
│   ├── main.py                   # FastAPI Application Entrypoint (Port 8002)
│   ├── logging_config.py         # Centralized Structured Logging Configuration
│   ├── games/
│   │   └── trivia.py             # Server Lore Dynamic Trivia Engine (8+ Questions, 3 Difficulties)
│   ├── media/
│   │   ├── gemini_image.py       # Gemini Native Image Generation Client (Free)
│   │   ├── meme_generator.py     # Pillow Text-Overlay Image Renderer
│   │   └── tts.py                # Edge-TTS Multi-Language Neural Voice Synthesizer (19 Voices)
│   ├── memory/
│   │   ├── db.py                 # Async Supabase Client & CRUD Operations (asyncio.to_thread)
│   │   ├── embeddings.py         # Gemini 768-dim Vector Embeddings
│   │   ├── episodic.py           # Background User Fact Extraction
│   │   ├── metrics.py            # Latency & Token Metric Auditing
│   │   ├── rag.py                # Vector Similarity RAG Search
│   │   ├── xp.py                 # XP & Reputation System Logic
│   │   └── schema.sql            # Supabase pgvector Database Schema (9 Tables)
│   ├── middleware/
│   │   └── rate_limiter.py       # Sliding-Window Rate Limiting + Body Cache Fix
│   ├── models/
│   │   ├── gemini_client.py      # Google AI Studio Gemini & Gemma Adapter
│   │   ├── kaggle_client.py      # Tunneled Kaggle GPU Worker Adapter
│   │   ├── openai_compatible_client.py # DigitalOcean & Ollama Adapter
│   │   └── router.py             # 3-Tier Explicit Model Router
│   ├── moderation/
│   │   └── content_filter.py     # AI Content Classification (safe/borderline/toxic)
│   ├── parsers/
│   │   └── file_parser.py        # PDF, DOCX, XLSX, Text & Vision Parser
│   ├── routers/
│   │   ├── admin.py              # Metrics, Memory Stats, XP Leaderboard & Purge Endpoints
│   │   ├── chat.py               # Chat Completion Engine (Type-Safe, BackgroundTasks)
│   │   ├── context.py            # Semantic Context Ranking Endpoint
│   │   ├── games.py              # Trivia Game Generator Endpoint
│   │   ├── github.py             # GitHub API Integration Endpoints
│   │   ├── lore.py               # Server Lore Vector CRUD Endpoints
│   │   ├── media.py              # TTS, Meme & AI Image Endpoints (Gemini + DO)
│   │   ├── model.py              # Model Status, Autocomplete & Set Endpoints
│   │   ├── moderation.py         # AI Moderation Check, Log & Settings Endpoints
│   │   ├── reminders.py          # Reminder CRUD & Delivery Endpoints
│   │   ├── sandbox.py            # Ephemeral Docker Code Execution Router
│   │   └── xp_router.py          # XP Award & Leaderboard Endpoints
│   ├── sandbox/
│   │   └── code_runner.py        # Docker Container Subprocess Sandbox
│   └── utils/
│       └── temp_manager.py       # Temp File Lifecycle Manager (Auto-Cleanup)
├── bot/
│   ├── client.py                 # Discord.py Gateway Bot, XP Hook, Moderation Hook
│   ├── stream_buffer.py          # Intelligent Multi-Message Chunking (>1900 chars)
│   ├── commands/
│   │   ├── admin_slash.py        # /admin memory & /admin channels Commands
│   │   ├── exec_slash.py         # /run Sandbox Command
│   │   ├── export_slash.py       # /export Conversation Export Command
│   │   ├── github_slash.py       # /github pr & /github issue Commands
│   │   ├── image_slash.py        # /image AI Art Command (Gemini + DO)
│   │   ├── meme_slash.py         # /meme Local Meme Renderer Command
│   │   ├── model_slash.py        # /model status & /model set Commands
│   │   ├── moderation_slash.py   # /moderation enable, sensitivity & log Commands
│   │   ├── privacy_slash.py      # /forget & /privacy Commands
│   │   ├── remember_slash.py     # /remember Server Lore Command
│   │   ├── remind_slash.py       # /remind Scheduled Reminder Command
│   │   ├── stats_slash.py        # /stats Analytics Command
│   │   ├── summarize_slash.py    # /summarize Thread Summary Command
│   │   ├── trivia_slash.py       # /trivia Interactive Quiz Command
│   │   ├── voice_slash.py        # /tts & /voice Commands
│   │   └── xp_slash.py           # /rank & /leaderboard Commands
│   └── plugins/
│       └── __init__.py           # Auto-Discovery Plugin Loader
├── infra/
│   └── pm2.config.js             # PM2 Production Ecosystem File (PYTHONPATH)
├── .env.example                  # Environment Configuration Template
├── requirements.txt              # Python Package Dependencies
├── USER_GUIDE.md                 # Complete User Manual (v3.0)
├── DEPLOYMENT.md                 # Deployment & Infrastructure Guide
├── PRIVACY.md                    # Privacy Policy Document
└── README.md                     # Open-Source Project Documentation (v3.0)
```

---

## 🔧 Installation & Deployment

### Prerequisites
* **Python**: 3.11 or higher
* **Docker Engine**: Installed and running on host
* **PM2**: Node.js process manager installed globally (`npm install -g pm2`)
* **Supabase Account**: With `pgvector` extension enabled

### 1. Clone Repository & Environment Setup
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
Run the SQL queries in `backend/memory/schema.sql` inside your Supabase SQL Editor to initialize all 9 tables: `channel_profiles`, `model_selections`, `guild_configs`, `user_memories`, `server_lore` (with vector index and RPC function), `request_logs`, `user_stats`, `scheduled_reminders`, and `moderation_log`.

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

* **Rate Limiting**: Sliding-window rate limit enforces **30 req/min per guild** and **10 req/min per user** to prevent API abuse. Request body properly cached to prevent body consumption bugs.
* **Sandbox Isolation**: Executed code runs inside non-root Docker containers with zero network access and 256MB RAM caps.
* **Structured Logging**: All components use Python `logging` with centralized configuration. Logs written to `logs/zauq.log` with rotation.
* **Async Safety**: All synchronous Supabase calls are wrapped in `asyncio.to_thread()` to prevent event loop blocking.
* **Data Guarantee**: User message contents are processed in real-time and **never stored or used for third-party model training**.
* **Right to be Forgotten**: Users can run `/forget` to permanently remove all stored vector facts associated with their Discord ID.

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

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

*Built with ❤️ by Syed Muhammad Hassan for the global developer and Discord community.*
