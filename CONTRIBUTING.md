# Contributing to Zauq

First off, thank you for considering contributing to Zauq! It's people like you that make Zauq such a powerful, community-driven AI engine.

## 🚀 Getting Started

### 1. Prerequisites
- **Python 3.11+**
- **Docker** & **Docker Compose** (Required for the `/run` code execution sandbox and local Supabase instance)
- **Discord Bot Token** (Create an app in the [Discord Developer Portal](https://discord.com/developers/applications))

### 2. Local Setup

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/YOUR-USERNAME/Zauq.git
   cd Zauq
   ```

2. **Set Up Python Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Environment Variables**:
   Copy the example config and fill in your keys:
   ```bash
   cp .env.example .env
   ```

4. **Run Backend and Bot**:
   Using Docker Compose (Easiest):
   ```bash
   docker-compose up --build
   ```
   Or manually:
   ```bash
   # Terminal 1: Backend
   python -m uvicorn backend.main:app --port 8002 --reload

   # Terminal 2: Bot
   python -m bot.client
   ```

## 🧪 Testing

Before submitting a Pull Request, please ensure all validation test suites pass. Zauq has a comprehensive set of automated tests:

```bash
# 1. Test Code Execution Sandbox
python -m backend.utils.test_sandbox_suite

# 2. Test Security, SSRF & Input Bounds
python -m backend.utils.test_security_hardening

# 3. Test Deep Web Search Engine
python -m backend.utils.test_deep_search

# 4. Test Specifications & Info Commands
python -m backend.utils.test_info_command

# 5. Test Reference & Reply Ingestion
python -m backend.utils.test_reply_ingestion
```

## 📝 Submitting a Pull Request
1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Commit your changes: `git commit -m 'Add some feature'`
3. Push to the branch: `git push origin feature/your-feature-name`
4. Open a Pull Request on GitHub.

*Please ensure your code follows standard Python conventions and does not break the `test_security_hardening.py` suite!*
