# Zauq VPS Deployment Guide — Contabo VPS Setup

This guide walks through deploying **Zauq** (FastAPI Backend + Discord Bot Client + Local Ollama) to your Contabo VPS using PM2.

---

## 1. Prerequisites on Contabo VPS
Make sure Python 3.10+, Node.js, and Git are installed on your VPS.

---

## 2. Install & Configure Local Ollama (Tier 2)

Run the following commands on your VPS terminal:

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. Pull Qwen3.5 4B model
ollama pull qwen3.5:4b

# 3. Verify local model output
ollama run qwen3.5:4b "hello"
```

---

## 3. Clone Repository & Environment Setup

```bash
# 1. Clone or sync your repository to the VPS
git clone <your-repo-url> /var/www/zauq
cd /var/www/zauq

# 2. Create python virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install requirements
pip install -r requirements.txt
```

---

## 4. Configure `.env` File on VPS

Create or update `/var/www/zauq/.env`:

```env
# Discord Bot Connection
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# LLM Providers
GEMINI_API_KEY=your_gemini_api_key_here
DO_MODEL_ACCESS_KEY=your_digitalocean_gradient_access_key_here
OLLAMA_BASE_URL=http://localhost:11434
KAGGLE_TUNNEL_URL=

# Database (Supabase)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_key

# Backend Server Settings
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8002
INTERNAL_API_KEY=your_random_64_char_hex_secret_here
```

---

## 5. Launch Processes using PM2

```bash
# 1. Install PM2 globally (if not already installed)
npm install -g pm2

# 2. Start Zauq Backend & Discord Bot via PM2
pm2 start infra/pm2.config.js

# 3. Save PM2 state for automatic server reboot recovery
pm2 save
pm2 startup
```

---

## 6. PM2 Command Reference

```bash
# View running process status
pm2 status

# View live backend & bot logs
pm2 logs zauq-backend
pm2 logs zauq-bot

# Restart services
pm2 restart all
```
