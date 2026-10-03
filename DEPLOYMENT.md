# 🚀 Zauq (ذوق) v4.0.0 Production Deployment & Migration Guide

This guide walks through deploying **Zauq v4.0.0** to production using either **Docker Compose** (recommended for production security with Docker socket isolation) or **PM2 process supervision** (VPS/bare-metal).

---

## 1. Prerequisites

* **Operating System:** Linux (Ubuntu 22.04 LTS / Debian 12 recommended)
* **Python:** Python 3.11+
* **Container Runtime:** Docker Engine 24.0+ and Docker Compose v2.20+
* **Process Manager:** PM2 (optional if running bare-metal: `npm install -g pm2`)
* **Database:** Supabase PostgreSQL with `pgvector` extension enabled
* **Discord Application:** Bot Token with Privileged Gateway Intents (Message Content, Server Members) enabled in [Discord Developer Portal](https://discord.com/developers/applications)

---

## 2. v4 Production Architecture

```text
                              ┌──────────────────────────────────────────┐
                              │           Discord Gateway (WS)           │
                              │   Voice Notes · Messages · Slash Tree    │
                              └────────────────────┬─────────────────────┘
                                                   │
                                      ┌────────────▼───────────┐
                                      │   zauq-bot Container   │
                                      │   discord.py Frontend  │
                                      └────────────┬───────────┘
                                                   │ HTTP
                                      ┌────────────▼───────────┐
                                      │ zauq-backend Container │
                                      │ FastAPI Bounded Engine │
                                      │ (No Docker Socket Access)
                                      └─────┬──────────────┬───┘
                                            │              │
                   Internal Authenticated   │              │
                    HTTP (X-Internal-Token) │              │
                               ┌────────────▼─────────┐    │
                               │ zauq-sandbox-runner  │    │
                               │ Isolated Runner API  │    │
                               └────────────┬─────────┘    │
                                            │              │
                                ┌───────────▼───────────┐  │
                                │   Docker Socket       │  │
                                │ (/var/run/docker.sock)│  │
                                └───────────────────────┘  │
                                                           │
                                ┌──────────────────────────▼───┐
                                │      Supabase PostgreSQL     │
                                │ (pgvector Semantic & Lore)   │
                                └──────────────────────────────┘
```

---

## 3. Database Migration (from v3 to v4)

In your Supabase project dashboard, navigate to the **SQL Editor** and run the additive v4 schema migrations from `backend/memory/schema.sql`:

```sql
-- 1. Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Pending Actions Table for Human-in-the-Loop confirmations (Phase 7)
CREATE TABLE IF NOT EXISTS pending_actions (
    action_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    guild_id TEXT,
    channel_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    risk TEXT NOT NULL DEFAULT 'write',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    executed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_pending_actions_user_status ON pending_actions (user_id, status);
CREATE INDEX IF NOT EXISTS idx_pending_actions_expires_at ON pending_actions (expires_at);

-- 3. Additive columns for existing channel_profiles table
ALTER TABLE channel_profiles
    ADD COLUMN IF NOT EXISTS auto_code_test_mode TEXT NOT NULL DEFAULT 'off' CHECK (auto_code_test_mode IN ('off', 'auto', 'always'));

-- 4. Additive columns for existing request_logs table (Observability & Cost tracking)
ALTER TABLE request_logs
    ADD COLUMN IF NOT EXISTS tool_steps INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS search_calls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pages_fetched INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS sandbox_calls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS mcp_calls INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS tool_failures INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS agent_duration_ms INT,
    ADD COLUMN IF NOT EXISTS input_tokens INT,
    ADD COLUMN IF NOT EXISTS output_tokens INT,
    ADD COLUMN IF NOT EXISTS estimated_cost_usd DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS request_id TEXT,
    ADD COLUMN IF NOT EXISTS agent_run_id TEXT;
```

---

## 4. Production Deployment with Docker Compose (Recommended)

### Step 1: Clone Repository
```bash
git clone https://github.com/Muhammad-Hassan12/Zauq-v4.git /opt/zauq
cd /opt/zauq
```

### Step 2: Configure Environment
```bash
cp .env.example .env
nano .env
```
Fill in your credentials:
* `DISCORD_BOT_TOKEN`: Discord Bot Token
* `GEMINI_API_KEY`: Google AI Studio API key
* `SUPABASE_URL` and `SUPABASE_KEY`: Supabase project URL and service role secret key
* `INTERNAL_API_KEY`: Strong random secret (e.g. `openssl rand -hex 32`)
* `SERPER_API_KEY`: Serper.dev API key for Google search

### Step 3: Pull Sandbox Base Images
Pre-pull the lightweight sandbox container images to avoid cold-start delays:
```bash
docker pull python:3.11-slim
docker pull node:18-alpine
docker pull alpine:latest
```

### Step 4: Build & Launch Services
```bash
docker compose up -d --build
```
This automatically deploys:
1. `zauq-sandbox-runner`: Isolated microservice mounting `/var/run/docker.sock` on port 8001.
2. `zauq-backend`: FastAPI engine running on port 8002 without Docker privileges.
3. `zauq-bot`: Discord gateway bot connected to the backend.

### Step 5: Verify Service Health
```bash
# Check running containers
docker compose ps

# Check sandbox runner health
curl http://127.0.0.1:8001/health
# Expected: {"status":"ok","service":"sandbox-runner"}

# Check backend health
curl http://127.0.0.1:8002/api/model/providers
```

---

## 5. Alternative VPS Bare-Metal Deployment with PM2

If running directly on a Linux VPS without containerizing the backend:

```bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 3. Pre-pull sandbox images
docker pull python:3.11-slim
docker pull node:18-alpine
docker pull alpine:latest

# 4. Start isolated sandbox runner (Terminal 1 or PM2)
python -m uvicorn backend.sandbox.runner_service:app --host 127.0.0.1 --port 8001 &

# 5. Launch with PM2
pm2 start infra/pm2.config.js
pm2 save
pm2 startup
```

---

## 6. Step-by-Step v4 Migration & Safe Rollout Order

Do **not** enable every new v4 feature simultaneously on production servers. Follow this staged rollout:

```text
Development / Local Testing
           ↓
Private Discord Test Channel / Staff Server
           ↓
Agent Runtime Enabled for One Test Guild
           ↓
Serper Search Enabled for Production
           ↓
Auto Sandbox Testing (Channel Opt-in)
           ↓
MCP Read-Only Tools Enabled
           ↓
MCP Approval-Based Write Tools Enabled
           ↓
General Rollout across All Guilds
```

### Rollout Milestones

1. **Phase 1 — Baseline Stability:**
   Deploy code with default feature flags:
   * `AGENT_RUNTIME_ENABLED=false`
   * `MCP_ENABLED=false`
   * `AUTO_CODE_TEST_DEFAULT=off`
   Verify that all existing chat, slash commands, voice TTS, and document reading continue to function normally.

2. **Phase 2 — Enable Serper Search:**
   Set `SERPER_API_KEY` and verify `/search` produces clean organic results with live web evidence.

3. **Phase 3 — Test Channel Agent Verification:**
   On a private test server or dedicated bot channel, test bounded tool execution:
   * Set `AGENT_RUNTIME_ENABLED=true` in `.env` or enable for a test guild.
   * Send queries requiring web search: *"What is the latest release of Python?"*
   * Send queries requiring code execution: *"Run a python script to calculate the first 10 fibonacci numbers."*
   * Verify bounded loop terminates within 4 steps and logs metrics in `request_logs`.

4. **Phase 4 — Human Confirmation Validation:**
   Trigger an action with `risk: write` or `risk: destructive`.
   Verify the bot posts an interactive Discord embed with **Approve** and **Deny** buttons, requiring user authorization before executing.

5. **Phase 5 — Model Context Protocol (MCP) Rollout:**
   * Configure read-only tools in `config/mcp_servers.json`.
   * Set `MCP_ENABLED=true` and verify status with `/mcp status`.
   * Test `/mcp tools` in scoped guilds.
   * Only promote write tools to production after testing confirmation dialogs.

---

## 7. Logs & Maintenance

```bash
# View backend logs in Docker
docker compose logs -f backend

# View sandbox runner logs
docker compose logs -f sandbox-runner

# View Discord bot logs
docker compose logs -f bot

# Restart individual service
docker compose restart backend
```
