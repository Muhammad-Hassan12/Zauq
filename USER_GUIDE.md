# 🤖 Zauq — Complete Master Guide & Documentation

**Zauq** is an AgenticEra Hybrid AI Discord Bot built on a high-performance **FastAPI backend engine** and a **`discord.py` thin-client frontend**. It features an explicit 3-Tier model selection router, a 3-Layer vector memory architecture (pgvector), isolated Docker code execution, free neural TTS voice synthesis, local meme rendering, and interactive mini-games.

---

## 📐 1. Architecture Overview

Zauq is split into two isolated processes running under PM2:
1. **FastAPI Engine (`zauq-backend`)**: Listens on `http://127.0.0.1:8002`. Handles AI prompt routing, vector embeddings, memory extraction, code execution sandboxing, and media rendering.
2. **Discord Bot Client (`zauq-bot`)**: Thin client connecting via WebSocket Gateway. Listens for message mentions, thread conversations, and 14 slash commands, sending requests to the FastAPI backend.

```
                  ┌─────────────────────────────────────────┐
                  │          Discord Gateway (WS)           │
                  └────────────────────┬────────────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │   Zauq Bot (discord.py)   │
                         └─────────────┬─────────────┘
                                       │ HTTP (Port 8002)
                         ┌─────────────▼─────────────┐
                         │   FastAPI Backend Engine  │
                         └──────┬──────────────┬─────┘
                                │              │
              ┌─────────────────▼───┐      ┌───▼────────────────┐
              │  Supabase pgvector  │      │  Docker Sandbox    │
              │  (Memories & Lore)  │      │  (Python/JS/Bash)  │
              └─────────────────────┘      └────────────────────┘
```

---

## 🎭 2. Operating Modes & Persona Configuration

Zauq operates in two distinct, per-channel modes configured via `/mode`:

### 🛠️ Dev Mode (`dev`)
- **Focus**: Technical assistance, code reviews, stack trace analysis, and sandboxed code execution.
- **Temperature**: Low (~`0.2`) for maximum precision and deterministic logic.
- **Persona**: Senior Software Engineer & Architect (concise, direct, highly technical).
- **Code Execution**: Enabled by default (`allow_code_exec = true`).

### 💬 Hangout Mode (`hangout`)
- **Focus**: Casual server companion, banter, server lore recall, memes, voice TTS, and trivia games.
- **Temperature**: High (~`0.75`) for expressive, witty, and creative responses.
- **Persona**: Expressive, funny, and engaging community companion.
- **Code Execution**: Disabled by default (`allow_code_exec = false`).

#### Switch Channel Mode Command:
```
/mode mode:dev        -> Locks channel to Dev Mode (low temp, technical)
/mode mode:hangout    -> Locks channel to Hangout Mode (casual, high temp)
```

---

## ⚡ 3. Explicit Model Tier Routing Engine

Unlike traditional bots with automatic cascade fallbacks, Zauq uses **explicit channel locking** (§1.2). Whatever tier is selected serves **every request** for that channel until manually changed.

| Tier | Provider / Engine | Details |
|---|---|---|
| Tier 1 | Gemini 2.5 Flash / Pro | Google AI Studio (`gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3.6-flash`, `gemini-3-pro-preview`) |
| Tier 1 | Gemma Family | Google AI Studio (`gemma-4-26b-a4b-it`, `gemma-4-31b-it`) |
| Tier 1 | DigitalOcean Gradient | Serverless Inference (`kimi-k3`, `glm-5.1`, `glm-5.2`, `deepseek-v4-pro`, `deepseek-4-flash`, `qwen3.5-397b-a17b`, `llama3.3-70b-instruct`) |
| Tier 2 | Local Ollama (`localhost:11434`) | Local VPS Model (`qwen3.5:4b` - zero API cost) |
| Tier 3 | Kaggle T4 Tunnel | Cloudflared Tunneled GPU Worker (`qwen3.5-t4`) |

#### Model Management Commands:
```
/model status                               -> Check active tier, provider, model, and updater
/model set tier:1 provider:gemini           -> Lock channel to Gemini 2.5 Flash
/model set tier:1 provider:gemini model:gemini-2.5-pro -> Lock channel to Gemini 2.5 Pro
/model set tier:1 provider:digitalocean model:deepseek-v4-pro -> Lock channel to DO DeepSeek v4 Pro
/model set tier:2 provider:ollama           -> Lock channel to local Ollama qwen3.5:4b
/model set tier:3 provider:kaggle           -> Lock channel to Kaggle T4 tunnel
```

---

## 📄 4. Universal Document & Attachment Ingestion

Zauq automatically reads attached files in Discord without needing separate commands:
- **Code & Text**: `.txt`, `.py`, `.js`, `.ts`, `.html`, `.css`, `.json`, `.yaml`, `.md`, `.log`, `.sql`, `.sh`
- **PDF Documents**: `.pdf` (text extracted page-by-page)
- **Word Documents**: `.docx` (paragraphs and tables extracted)
- **Spreadsheets**: `.csv`, `.xlsx` (converted into Markdown tables)
- **Images & Vision**: `.png`, `.jpg`, `.jpeg`, `.webp` (sent natively to Gemini Multimodal Vision)


---

## 🧠 4. Memory Architecture (How Zauq Remembers)

Zauq maintains context across 3 distinct memory layers:

1. **L1 Working Context Window**:
   - Automatically fetches the last **15 messages** in a thread or channel.
   - Auto-spawns a Discord Thread when a user mentions Zauq in a main channel to keep multi-turn conversations organized.

2. **L2 User Episodic Facts (`user_memories`)**:
   - Post-response background worker analyzes conversation transcripts.
   - Automatically extracts user facts (e.g. tech stack, handle, preferences) and embeds them as 3072-dimensional vectors using `gemini-embedding-001`.
   - Injected into system prompt whenever the user chats with Zauq.

3. **L3 Server Lore RAG (`server_lore`)**:
   - Knowledge base containing server rules, inside jokes, documentation, or ingested GitHub READMEs.
   - Vector similarity search (`match_server_lore` pgvector RPC) retrieves top-3 matching facts and grounds the model's answer.

---

## 📜 5. Complete Slash Command Reference (All 14 Commands)

| Command | Category | Description & Usage |
|---|---|---|
| `/mode` | Core | Switch channel operating mode (`dev` or `hangout`). |
| `/model status` | Models | Display current model tier, provider, and model name for this channel. |
| `/model set` | Models | Set channel model tier (1, 2, 3), provider, and model name (with DO autocomplete). |
| `/run` | Sandbox | Safely execute code snippets (`python`, `javascript`, `bash`) in an isolated Docker container. |
| `/remember` | Lore | Save a server lore fact, rule, or inside joke into vector memory. |
| `/github pr` | GitHub | Fetch and summarize a GitHub Pull Request diff (`repo: owner/name pr_number: 12`). |
| `/github issue` | GitHub | Fetch and display a GitHub Issue description. |
| `/ingest_repo` | GitHub | Ingest a GitHub repository README into server vector lore memory. |
| `/tts` | Voice | Convert text into high-quality neural voice speech (`.mp3` output). |
| `/voice join` | Voice | Connect Zauq to your current voice channel. |
| `/voice leave` | Voice | Disconnect Zauq from the voice channel. |
| `/meme` | Media | Render text-overlay memes with impact font and outline styling (`top_text`, `bottom_text`). |
| `/image` | Media | Generate AI visual art cards from a text prompt. |
| `/trivia` | Games | Launch an interactive multiple-choice trivia mini-game using Discord UI buttons. |
| `/stats` | Admin | View server request volume, average response latency, and provider breakdown. |
| `/forget` | Privacy | Purge all stored episodic memory facts associated with your Discord User ID. |
| `/privacy` | Privacy | Display Zauq data privacy disclosure and zero model-training guarantees. |

---

## ⚙️ 6. Sandboxed Code Execution (`/run`)

Code execution runs inside isolated, ephemeral Docker containers:
- **Languages**: Python 3 (`python:3.11-slim`), JavaScript (`node:18-alpine`), Bash (`alpine:latest`).
- **Security Limits**: `--network none` (no internet access), `--memory 256m`, `--cpus 0.5`, 5.0 second timeout.
- **Permission Gate**: Gated behind `channel_profiles.allow_code_exec` (enabled in `dev` mode, restricted in `hangout` mode).

#### Example Usage:
```
/run code: print([x**2 for x in range(10)]) language: Python 3
/run code: console.log(Array.from({length: 5}, (_, i) => i * 10)); language: JavaScript
/run code: echo "Current Date: $(date)" language: Bash
```

---

## 🔊 7. Free Neural TTS & Voice Companion

- **Engine**: Microsoft Edge Neural TTS (`edge-tts`). Zero API cost, < 1% CPU load (cloud-synthesized).
- **Voice Options**:
  - `christopher`: US Male (Deep, clear)
  - `ava`: US Female (Expressive)
  - `guy`: US Male (Casual)
  - `sonia`: UK Female (British accent)
  - `brian`: UK Male (British accent)

#### Example Usage:
```
/tts text: Zauq systems are fully operational and ready for deployment. voice: Christopher (US Male)
```

---

## 🔒 8. Security, Rate Limits & Privacy

1. **Rate Limiting Middleware**:
   - Per-Guild Limit: Max **30 requests / minute**.
   - Per-User Limit: Max **10 requests / minute**.
   - Returns HTTP `429 Too Many Requests` when limits are exceeded.

2. **Zero Model-Training Guarantee**:
   - Message data is processed strictly in real-time to generate responses.
   - **No user messages are ever used to fine-tune or train third-party models.**

3. **Data Deletion Rights**:
   - Users can invoke `/forget` at any time to permanently wipe their stored vector memories from Supabase.

---

## 🔧 9. Process Management (PM2 Commands)

To manage Zauq on your VPS:

```bash
# Check status of all processes (ustaad-api, agenticera-backend, zauq-backend, zauq-bot)
pm2 status

# View live Zauq backend & bot logs
pm2 logs zauq-backend
pm2 logs zauq-bot

# Restart Zauq services
pm2 restart zauq-backend zauq-bot

# Save process state for automatic reboot recovery
pm2 save
```

---
*Created for Hassan / AgenticEra Systems — Zauq v2.0 Master Documentation*
