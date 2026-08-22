import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # Discord
    DISCORD_BOT_TOKEN: str = ""

    # LLM Providers
    GEMINI_API_KEY: str = ""
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
    GITHUB_ALLOWED_REPOS: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
