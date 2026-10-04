import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Discord
    DISCORD_BOT_TOKEN: str = ""

    # LLM Providers
    GEMINI_API_KEY: str = ""
    GEMINI_DEFAULT_MODEL: str = "gemini-2.5-flash"
    DO_MODEL_ACCESS_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    KAGGLE_TUNNEL_URL: str = ""

    # Database
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # App Settings
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8002
    INTERNAL_API_KEY: str = ""
    # Secondary key required by /api/admin/* endpoints. If blank, falls back to INTERNAL_API_KEY so existing single-key deployments continue to work.
    ADMIN_API_KEY: str = ""
    DEVELOPMENT_MODE: bool = False
    GITHUB_ALLOWED_REPOS: str = ""

    # ── v4 Agent Runtime ──────────────────────────────────────────────────────
    # All disabled by default. Existing behavior is fully preserved.
    AGENT_RUNTIME_ENABLED: bool = False
    AGENT_ALLOWED_GUILD_IDS: str = ''
    AGENT_ALLOWED_CHANNEL_IDS: str = ''
    MCP_ALLOWED_GUILD_IDS: str = ''
    MCP_ALLOWED_CHANNEL_IDS: str = ''
    AGENT_MAX_TOOL_STEPS: int = 4
    AGENT_DEEP_MAX_TOOL_STEPS: int = 6

    # ── v4 Web Search ─────────────────────────────────────────────────────────
    SERPER_API_KEY: str = ""
    WEB_SEARCH_PROVIDER: str = "serper"
    WEB_FETCH_MAX_BYTES: int = 1000000
    WEB_SEARCH_CACHE_TTL_SECONDS: int = 300
    WEB_SEARCH_MAX_RESULTS: int = 5
    WEB_FETCH_MAX_PAGES: int = 3
    GEMINI_NATIVE_GROUNDING_ENABLED: bool = False

    # ── v4 MCP ────────────────────────────────────────────────────────────────
    MCP_ENABLED: bool = False
    MCP_CONFIG_PATH: str = "config/mcp_servers.json"
    MCP_MAX_SERVERS: int = 5
    MCP_MAX_CONCURRENCY: int = 4
    MCP_DEFAULT_TIMEOUT_SECONDS: float = 20.0

    # ── v4 Observability & VPS Protection (Phase 11) ───────────────────────────
    WEB_FETCH_CONCURRENCY: int = 3
    AGENT_TOTAL_TIMEOUT_SECONDS: float = 90.0
    AGENT_DEEP_RESEARCH_TIMEOUT_SECONDS: float = 180.0
    FILE_GENERATION_TIMEOUT_SECONDS: float = 600.0
    MODEL_PRICING_JSON: str = '{}'

    # ── v4 Sandbox ────────────────────────────────────────────────────────────
    SANDBOX_RUNNER_URL: Optional[str] = ""   # e.g. "http://sandbox-runner:8001" for isolated runner
    SANDBOX_MAX_CONCURRENCY: int = 1
    SANDBOX_DEFAULT_TIMEOUT_SECONDS: int = 8
    SANDBOX_MAX_OUTPUT_CHARS: int = 12000
    SANDBOX_SPOOL_DIR: str = ''
    SANDBOX_HOST_SPOOL_DIR: str = ''
    AUTO_CODE_TEST_DEFAULT: str = "off"      # "off" | "auto" | "always"
    AUTO_CODE_REPAIR_ATTEMPTS: int = 1

    # ── v4 New Tier-1 Providers ───────────────────────────────────────────────
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: str = "https://api.anthropic.com"
    ANTHROPIC_DEFAULT_MODEL: str = "claude-sonnet-4-5"

    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = ""                  # Region/workspace-specific; set in .env
    QWEN_DEFAULT_MODEL: str = "qwen-turbo"

    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_DEFAULT_MODEL: str = "deepseek-flash"

    model_config = SettingsConfigDict(
        env_file=os.environ.get('ZAUQ_ENV_FILE', '.env'),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
