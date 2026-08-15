# 🤖 Zauq — Complete Master Guide & Documentation (v3.0)

**Zauq (ذوق)** is an AgenticEra Hybrid AI Discord Bot built on a high-performance **FastAPI backend engine** and a **`discord.py` thin-client frontend**. It features an explicit 3-Tier model selection router, a 3-Layer vector memory architecture (pgvector), isolated Docker code execution, free neural TTS voice synthesis, AI image generation, AI content moderation, an XP/reputation system, and interactive mini-games.

---

## 📐 1. Architecture Overview

Zauq is split into two isolated processes running under PM2:
1. **FastAPI Engine (`zauq-backend`)**: Listens on `http://127.0.0.1:8002`. Handles AI prompt routing, vector embeddings, memory extraction, code execution sandboxing, media rendering, XP tracking, reminders, and content moderation.
2. **Discord Bot Client (`zauq-bot`)**: Thin client connecting via WebSocket Gateway. Listens for message mentions, thread conversations, and 21 slash commands, sending requests to the FastAPI backend.

```
                  ┌─────────────────────────────────────────┐
                  │          Discord Gateway (WS)           │
                  └────────────────────┬────────────────────┘
                                       │
                         ┌─────────────▼──────────────┐
                         │   Zauq Bot (discord.py)    │
                         │   21 Slash Commands + XP   │
                         └─────────────┬──────────────┘
                                       │ HTTP (Port 8002)
                         ┌─────────────▼─────────────┐
                         │   FastAPI Backend Engine  │
                         │  Router · Memory · Media  │
                         │  Moderation · XP · Tasks  │
                         └──────┬──────────────┬─────┘
                                │              │
              ┌─────────────────▼───┐      ┌───▼────────────────┐
              │       pgvector      │      │  Docker Sandbox    │
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
- **Focus**: Casual server companion, banter, server lore recall, memes, voice TTS, trivia games, and community engagement.
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

Unlike traditional bots with automatic cascade fallbacks, Zauq uses **explicit channel locking**. Whatever tier is selected serves **every request** for that channel until manually changed.

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
- **PDF Documents**: `.pdf` (text extracted page-by-page via `pypdf`)
- **Word Documents**: `.docx` (paragraphs and tables extracted via `python-docx`)
- **Spreadsheets**: `.csv`, `.xlsx` (converted into Markdown tables via `openpyxl`)
- **Images & Vision**: `.png`, `.jpg`, `.jpeg`, `.webp` (sent natively to Gemini Multimodal Vision for screenshot/diagram analysis)

**Usage**: Simply attach a file to your message when mentioning @Zauq. The file is automatically parsed and included in the AI context.

---

## 🧠 5. Memory Architecture (How Zauq Remembers)

Zauq maintains context across 3 distinct memory layers:

### L1 — Working Context Window
- Automatically fetches the last **15 messages** in a thread or channel.
- Auto-spawns a Discord Thread when a user mentions Zauq in a main channel to keep multi-turn conversations organized.
- Intelligent message chunking: messages over 1,900 characters are split at line breaks and code block boundaries to preserve Markdown formatting.

### L2 — User Episodic Facts (`user_memories`)
- Post-response background worker analyzes conversation transcripts using the active AI model.
- Automatically extracts user facts (e.g. tech stack, name, preferences, project context) and embeds them as **768-dimensional vectors** using `gemini-embedding-001`.
- Stored facts are injected into the system prompt whenever the user chats with Zauq, giving it persistent memory of each user.

### L3 — Server Lore RAG (`server_lore`)
- Knowledge base containing server rules, inside jokes, documentation, or ingested GitHub READMEs.
- Vector similarity search (`match_server_lore` pgvector RPC) retrieves top-3 matching facts and grounds the model's answer in server-specific context.
- Lore is added via `/remember` or `/ingest_repo` and searched automatically during every chat.

---

## 📜 6. Complete Slash Command Reference (All 21 Commands)

### 🎯 Core Commands

| Command | Description | Usage Example |
|---|---|---|
| `/mode` | Switch channel operating mode | `/mode mode:dev` or `/mode mode:hangout` |
| `/summarize` | Summarize the current thread/channel into bullet points | `/summarize length:brief` or `/summarize length:detailed` |

**`/mode`** — Switches the channel between Dev Mode (technical, low temp) and Hangout Mode (casual, high temp). The mode is saved per-channel and persists across sessions.

**`/summarize`** — Fetches the last 50 messages from the current channel or thread and sends them to the active AI model with a summarization prompt. Returns a clean bullet-point summary embed. Supports `brief` (3-5 bullet points) and `detailed` (comprehensive) modes.

---

### 🤖 Model Management Commands

| Command | Description | Usage Example |
|---|---|---|
| `/model status` | View current model tier, provider, and model name | `/model status` |
| `/model set` | Set channel model tier, provider, and model name | `/model set tier:1 provider:gemini model:gemini-2.5-pro` |

**`/model status`** — Displays the currently active model for this channel, including the tier number, provider name, and specific model. Shows who last changed the model and when.

**`/model set`** — Locks the channel to a specific model tier and provider. Supports autocomplete for model names. Changes take effect immediately for all subsequent messages in the channel.

---

### ⚙️ Sandboxed Code Execution

| Command | Description | Usage Example |
|---|---|---|
| `/run` | Execute code safely in an isolated Docker container | `/run code:print("hello") language:Python 3` |

**`/run`** — Runs code snippets inside ephemeral, isolated Docker containers with the following security constraints:
- **Languages**: Python 3 (`python:3.11-slim`), JavaScript (`node:18-alpine`), Bash (`alpine:latest`)
- **Security**: `--network none` (no internet access), `--memory 256m`, `--cpus 0.5`, 5-second timeout
- **Access**: Gated behind `channel_profiles.allow_code_exec` — enabled by default in Dev Mode, disabled in Hangout Mode

```
/run code: print([x**2 for x in range(10)]) language: Python 3
/run code: console.log(Array.from({length: 5}, (_, i) => i * 10)); language: JavaScript
/run code: echo "Current Date: $(date)" language: Bash
```

---

### 🧠 Memory & Lore Commands

| Command | Description | Usage Example |
|---|---|---|
| `/remember` | Save a server lore fact, rule, or inside joke into vector memory | `/remember type:inside_joke fact:We call CI failures "oopsies"` |
| `/forget` | Purge all stored episodic memory facts for your User ID | `/forget` |
| `/privacy` | Display Zauq's data privacy disclosure | `/privacy` |

**`/remember`** — Stores a piece of server knowledge (rules, inside jokes, documentation, or facts) into the Supabase `server_lore` table with a 768-dim vector embedding. This lore is automatically retrieved via RAG during future conversations. Types: `rule`, `inside_joke`, `doc`, `repo`.

**`/forget`** — Permanently deletes all stored episodic user facts (L2 memory) associated with your Discord User ID from Supabase. This is irreversible and GDPR-compliant.

**`/privacy`** — Displays Zauq's data privacy policy, explaining what data is stored, how it's used, and the zero model-training guarantee.

---

### 🐙 GitHub Integration Commands

| Command | Description | Usage Example |
|---|---|---|
| `/github pr` | Fetch and summarize a GitHub Pull Request diff | `/github pr repo:owner/name pr_number:12` |
| `/github issue` | Fetch and display a GitHub Issue description | `/github issue repo:owner/name issue_number:5` |
| `/ingest_repo` | Ingest a GitHub repository README into server lore | `/ingest_repo repo:owner/name` |

**`/github pr`** — Fetches the diff and metadata for a GitHub Pull Request using the GitHub API, then summarizes the changes using the active AI model.

**`/github issue`** — Fetches and displays the title, body, labels, and status of a GitHub issue in a clean embed.

**`/ingest_repo`** — Downloads the README.md from a public GitHub repository and stores it as server lore in the vector database. This allows Zauq to answer questions about your project documentation using RAG search.

---

### 🔊 Voice & TTS Commands

| Command | Description | Usage Example |
|---|---|---|
| `/tts` | Generate high-quality neural voice speech | `/tts text:Hello world voice:Christopher (US Male)` |
| `/voice join` | Connect Zauq to your current voice channel | `/voice join` |
| `/voice leave` | Disconnect Zauq from the voice channel | `/voice leave` |

**`/tts`** — Converts text into high-quality neural speech using Microsoft Edge Neural TTS (zero API cost). Outputs an `.mp3` file uploaded as a Discord attachment. Supports **9 voices across 7 languages**:

| Voice | Language | Gender |
|---|---|---|
| `Christopher` | English (US) | Male |
| `Ava` | English (US) | Female |
| `Asad` | Urdu (PK) | Male |
| `Uzma` | Urdu (PK) | Female |
| `Madhur` | Hindi (IN) | Male |
| `Hamed` | Arabic (SA) | Male |
| `Alvaro` | Spanish (ES) | Male |
| `Henri` | French (FR) | Male |
| `Keita` | Japanese (JP) | Male |

Additional backend voices available (not in slash choice menu): `guy` (US Male), `sonia` (UK Female), `brian` (UK Male), `swara` (Hindi Female), `zariyah` (Arabic Female), `elvira` (Spanish Female), `denise` (French Female), `conrad` (German Male), `katja` (German Female), `nanami` (Japanese Female).

**`/voice join`** — Connects Zauq to the voice channel you're currently in.

**`/voice leave`** — Disconnects Zauq from the voice channel.

---

### 🖼️ Media Commands

| Command | Description | Usage Example |
|---|---|---|
| `/image` | Generate AI art from a text prompt | `/image prompt:a sunset over mountains` |
| `/meme` | Render text-overlay memes with impact font styling | `/meme top_text:When the code works bottom_text:On the first try` |

**`/image`** — Generates AI visual art from a text prompt. Supports 3 model providers:

| Model | Provider | Cost |
|---|---|---|
| `Gemini Flash Image` (Default) | Google AI Studio | **Free** |
| `Stable Diffusion 3.5 Large` | DigitalOcean Gradient | Paid |
| `Ideogram 3.0 Turbo` | DigitalOcean Gradient | Paid |

The default model is **Gemini Flash Image** which uses Google's `gemini-3.1-flash-image` model via the existing Gemini API key — **completely free**. Outputs a 1024x1024 PNG image attached as a Discord embed.

**`/meme`** — Renders a meme image locally using Pillow with Impact-style font and outline text. Customizable top/bottom text, background color, and text color. No API calls required.

---

### 🎮 Games & XP Commands

| Command | Description | Usage Example |
|---|---|---|
| `/trivia` | Play interactive trivia with difficulty levels & XP rewards | `/trivia difficulty:Hard` |
| `/rank` | View your XP level, server rank, and progress | `/rank` |
| `/leaderboard` | View top 10 server members by XP | `/leaderboard` |

**`/trivia`** — Launches an interactive multiple-choice trivia question with Discord UI buttons (A, B, C, D). Features:
- **Difficulty levels**: Easy, Medium, Hard — each with appropriately challenging questions
- **XP rewards**: +5 XP for correct answers, +1 XP for participation
- **Server lore trivia**: If server lore exists, trivia questions may be generated from your server's knowledge base
- **Tech topics**: Python, JavaScript, Linux, Databases, Networking, Git, Docker, AI/ML
- **60-second timeout** with auto-disable buttons

**`/rank`** — Shows your personal XP stats including: current XP total, level, server rank position, messages sent, commands used, trivia stats, and streak days. Displayed as a rich embed with a progress bar to the next level.

**`/leaderboard`** — Shows the top 10 users in the server ranked by XP. Displays username, XP total, level, and a visual bar chart. XP is earned through:
- Messages: **+1 XP** per message
- Commands: **+2 XP** per command used
- Trivia correct: **+5 XP** per correct answer
- Trivia participation: **+1 XP** per attempt

**Level Formula**: `level = floor(sqrt(xp / 100)) + 1`

---

### ⏰ Utility Commands

| Command | Description | Usage Example |
|---|---|---|
| `/remind` | Schedule a reminder message (1 min to 7 days) | `/remind message:Deploy to prod in_minutes:30` |
| `/export` | Export conversation history as a Markdown file | `/export format:markdown` |

**`/remind`** — Schedules a reminder that Zauq will post in the same channel after the specified number of minutes. Stored in the `scheduled_reminders` Supabase table. A background worker polls every 30 seconds for due reminders and posts them as embeds with a user mention.
- **Range**: 1 minute to 10,080 minutes (7 days)
- **Example**: `/remind message:"Review PR #42" in_minutes:60` → Zauq posts a reminder in 1 hour

**`/export`** — Fetches the last 100 messages from the current channel/thread and exports them as a formatted Markdown (`.md`) file uploaded as a Discord attachment. Preserves timestamps, usernames, and code blocks. Supports `markdown` and `text` formats.

---

### 🛡️ Moderation Commands (Admin)

| Command | Description | Usage Example |
|---|---|---|
| `/moderation enable` | Enable or disable AI content moderation for the server | `/moderation enable enabled:True` |
| `/moderation sensitivity` | Set AI content filtering sensitivity | `/moderation sensitivity level:high` |
| `/moderation log` | View recent moderation log entries | `/moderation log` |

**`/moderation enable`** — Toggles AI-powered content moderation for the server. When enabled, every message mentioning Zauq is first checked by an AI content filter before processing. Messages classified as `toxic` are automatically deleted, and the user receives a DM warning. Messages classified as `borderline` are logged for admin review. Requires **Administrator** permission.

**`/moderation sensitivity`** — Sets the sensitivity level of the AI content filter: `low` (only extreme content), `medium` (balanced), or `high` (strict filtering). Requires **Administrator** permission.

**`/moderation log`** — Displays the last 10 moderation actions taken in this server, including flagged messages, warnings issued, and deleted messages. Shows severity, action taken, and timestamp. Requires **Administrator** permission.

---

### 📊 Admin & Analytics Commands

| Command | Description | Usage Example |
|---|---|---|
| `/admin memory` | View server memory and lore vector stats | `/admin memory` |
| `/admin channels` | View channels with configured AI profiles | `/admin channels` |
| `/stats` | View server request volume, latency, and provider metrics | `/stats` |

**`/admin memory`** — Shows detailed memory statistics including: total user memories stored, total server lore entries, total API requests processed, and average response latency. Data sourced from Supabase. Requires **Administrator** permission.

**`/admin channels`** — Lists all channels in the server that have been configured with AI profiles (via `/mode` or `/model set`). Shows each channel's operating mode and temperature setting. Useful for auditing which channels Zauq is active in. Requires **Administrator** permission.

**`/stats`** — View server-level analytics: total request volume, average response latency, and provider breakdown (Gemini vs DO vs Ollama usage). Available to all users.

---

## 🏆 7. XP & Reputation System

Zauq tracks user engagement through an XP and leveling system:

### How XP is Earned
| Action | XP Reward |
|---|---|
| Sending a message (when Zauq is mentioned) | +1 XP |
| Using any slash command | +2 XP |
| Correct trivia answer | +5 XP |
| Trivia participation (wrong answer) | +1 XP |

### Leveling
- **Formula**: `Level = floor(sqrt(XP / 100)) + 1`
- **Level 1**: 0-99 XP
- **Level 2**: 100-399 XP
- **Level 3**: 400-899 XP
- **Level 4**: 900-1599 XP
- And so on (exponential scaling)

### Tracked Stats
- Total XP and Level
- Messages count
- Commands used
- Trivia correct / played
- Streak days (consecutive days of activity)
- Last active timestamp

---

## 🛡️ 8. AI Content Moderation

When enabled, Zauq uses AI to automatically moderate incoming messages:

### How It Works
1. Each message mentioning Zauq is sent to a lightweight AI classifier
2. The classifier categorizes it as: `safe`, `borderline`, or `toxic`
3. Actions are taken automatically based on severity:

| Classification | Action |
|---|---|
| `safe` | Message processed normally |
| `borderline` | Logged to `moderation_log` table for admin review |
| `toxic` | Message deleted + user receives DM warning |

### Configuration
- **Enable**: `/moderation enable enabled:True`
- **Sensitivity**: `/moderation sensitivity level:low|medium|high`
- **Audit**: `/moderation log` to review recent actions

All moderation actions are logged to the `moderation_log` Supabase table with: guild, channel, user, message content, action taken, severity, and reason.

---

## 🔌 9. Plugin System

Zauq supports community-made extensions through the plugin system:

### Creating a Plugin
1. Create a Python file in `bot/plugins/` (e.g., `my_plugin.py`)
2. The file must contain an `async def setup(bot)` entrypoint
3. Plugins are automatically discovered and loaded on bot startup

### Plugin Template
```python
import discord
from discord.ext import commands

class MyPlugin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="mycommand", description="My custom command")
    async def my_command(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hello from my plugin!")

async def setup(bot: commands.Bot):
    await bot.add_cog(MyPlugin(bot))
```

### Plugin Guidelines
- Plugins are loaded **after** all built-in cogs
- Each plugin file is loaded as a separate Discord extension
- Failed plugins are logged but don't crash the bot
- Place plugins in `/root/Zauq/bot/plugins/`

---

## 🔒 10. Security, Rate Limits & Privacy

### Rate Limiting Middleware
- Per-Guild Limit: Max **30 requests / minute**
- Per-User Limit: Max **10 requests / minute**
- Returns HTTP `429 Too Many Requests` when limits are exceeded
- Automatic cleanup of stale rate limit entries every 5 minutes

### Sandbox Security
- Executed code runs inside non-root Docker containers
- **`--network none`**: Zero network access
- **`--memory 256m`**: 256MB RAM cap
- **`--cpus 0.5`**: Half CPU core limit
- **5-second timeout**: Kills long-running processes
- Ephemeral containers: destroyed after execution

### Zero Model-Training Guarantee
- Message data is processed strictly in real-time to generate responses
- **No user messages are ever used to fine-tune or train third-party models**
- All AI providers (Google, DigitalOcean) are used via their API-only endpoints

### Data Deletion Rights (GDPR)
- Users can invoke `/forget` at any time to permanently wipe their stored vector memories from Supabase
- `/privacy` command displays full data handling disclosure

---

## 🔧 11. Process Management (PM2 Commands)

To manage Zauq on your VPS:

```bash
# Check status of all processes
pm2 status

# View live Zauq backend & bot logs
pm2 logs zauq-backend
pm2 logs zauq-bot

# Restart Zauq services only (safe — other apps untouched)
pm2 restart zauq-backend zauq-bot

# Restart with environment variable updates
pm2 restart zauq-backend zauq-bot --update-env

# Save process state for automatic reboot recovery
pm2 save

# View structured log file
tail -f /root/Zauq/logs/zauq.log
```

### Structured Logging
All Zauq components use Python's `logging` module with a centralized configuration:
- **Format**: `[timestamp] [LEVEL] [module_name] message`
- **Output**: Console + rotating file (`logs/zauq.log`)
- **Modules**: `zauq.bot`, `zauq.chat`, `zauq.media`, `zauq.rag`, `zauq.episodic`, `zauq.metrics`, `zauq.embeddings`, `zauq.trivia`, `zauq.plugins`, `zauq.admin`, `zauq.reminders`

---

## 🗄️ 12. Database Tables

Zauq uses the following Supabase tables:

| Table | Purpose |
|---|---|
| `channel_profiles` | Per-channel mode, temperature, and persona settings |
| `model_selections` | Per-channel model tier, provider, and model name |
| `guild_configs` | Per-guild default mode, moderation settings |
| `user_memories` | L2 episodic user facts with vector embeddings |
| `server_lore` | L3 server knowledge base with vector embeddings |
| `request_logs` | API request metrics (latency, model, provider) |
| `user_stats` | XP, level, messages, commands, trivia stats per user |
| `scheduled_reminders` | Pending and delivered reminder messages |
| `moderation_log` | AI moderation actions (flagged, warned, deleted) |

---

*Created for Syed Muhammad Hassan / AgenticEra Systems — Zauq v3.0 Master Documentation*
