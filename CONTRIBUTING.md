# Contributing to Zauq (ذوق) v4.0.0

First off, thank you for considering contributing to Zauq! We welcome contributions that keep Zauq reliable, secure, maintainable, and powerful.

---

## 🚀 Getting Started

### 1. Prerequisites
* **Python 3.11+**
* **Docker Engine** (Required for code execution sandboxing tests)
* **Discord Bot Token** (Create an app in the [Discord Developer Portal](https://discord.com/developers/applications))
* **Git**

### 2. Local Setup

1. **Fork and Clone**:
   ```bash
   git clone https://github.com/YOUR-USERNAME/Zauq.git
   cd Zauq
   ```

2. **Set Up Python Virtual Environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install pytest pytest-asyncio pytest-cov
   ```

3. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   ```
   Fill in your API credentials. During local development, feature flags can remain `false` by default.

4. **Run Services**:
   * **Using Docker Compose (Recommended)**:
     ```bash
     docker compose up --build
     ```
   * **Or Manually (Multi-Terminal)**:
     ```bash
     # Terminal 1: Sandbox Runner (Optional isolated mode)
     python -m uvicorn backend.sandbox.runner_service:app --port 8001 --reload

     # Terminal 2: FastAPI Backend Engine
     python -m uvicorn backend.main:app --port 8002 --reload

     # Terminal 3: Discord Bot Client
     python -m bot.client
     ```

---

## 🧪 Testing Guidelines

Zauq v4 includes a modern, 7-stage test suite organized under `tests/` with 100% offline, deterministic coverage (zero paid LLM API calls in CI).

### Running All Tests
```bash
pytest tests/ -v
```

### Running Test Stages Individually

```bash
# 1. Unit Tests (Agent Runtime, Tool System, Models)
pytest tests/agent/ tests/tools/ tests/models/ -v

# 2. Search Subsystem (Query Optimizer, Research v2)
pytest tests/search/ -v

# 3. Model Context Protocol (MCP Client & Adapters)
pytest tests/mcp/ -v

# 4. Security Hardening (SSRF, Secret Sanitization, Prompt Injection)
pytest tests/security/ -v

# 5. Docker Sandbox Tests (Timeout, Concurrency, Permission Semantics)
pytest tests/sandbox/ -v

# 6. Integration & Regression Checklist Tests
pytest tests/integration/ tests/observability/ tests/actions/ tests/bot/ tests/chat/ -v
```

### Legacy Utility Suites (Backward Compatibility)
```bash
python -m backend.utils.test_security_hardening
python -m backend.utils.test_sandbox_suite
python -m backend.utils.test_deep_search
python -m backend.utils.test_info_command
python -m backend.utils.test_reply_ingestion
```

---

## 📐 Architecture & Coding Invariants

When adding new features or tools to Zauq v4, strictly maintain these core invariants:

1. **Tool System Contracts (`backend/tools/`)**:
   * Every tool must define a `ToolSpec` with canonical naming (`category.action` or `mcp.<server>.<action>`).
   * Tools must declare an explicit `RiskLevel` (`read`, `write`, `destructive`, `privileged`).
   * Any tool with `write` or `destructive` risk **must require human approval** via the `ActionService`.

2. **Bounded Execution (`backend/agent/`)**:
   * Never introduce unbounded recursive autonomous loops.
   * Tool calls are strictly bounded by `AgentBudget` (max 4 steps normal, max 6 steps deep search).
   * Repeated identical tool calls must trigger the loop detection guard.

3. **Security & Untrusted Data Fencing (`backend/security/`)**:
   * All external web content, document attachments, and MCP outputs are **untrusted data**.
   * Tools must fence observations using `fence_tool_data()`.
   * Never leak API keys, tokens, or credentials into model context or user responses. Always route outputs through `sanitize_secrets()`.

4. **Zero Overhead When Disabled**:
   * Subsystems governed by feature flags (`AGENT_RUNTIME_ENABLED`, `MCP_ENABLED`) must consume zero background resources when disabled.

---

## 📝 Submitting a Pull Request

1. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Commit your changes with clear, descriptive commit messages.
3. Verify that the complete test suite passes:
   ```bash
   pytest tests/
   ```
4. Open a Pull Request on GitHub describing your changes and testing methodology.
