"""Centralized Provider & Model Catalog for Zauq AI.

Single source of truth for providers, models, tiers, capabilities,
and credential validation across bot and backend.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from backend.config import settings


@dataclass
class ProviderSpec:
    id: str
    display_name: str
    tier: int
    default_model: str
    models: List[str] = field(default_factory=list)
    credential_env_vars: List[str] = field(default_factory=list)
    supports_streaming: bool = True
    supports_native_tools: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    supports_thinking: bool = False


# Central Provider Catalog
PROVIDERS: Dict[str, ProviderSpec] = {
    "gemini": ProviderSpec(
        id="gemini",
        display_name="Google AI Studio (Gemini / Gemma)",
        tier=1,
        default_model="gemini-2.5-flash",
        models=[
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-3.6-flash",
            "gemini-3.5-flash",
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemma-4-26b-a4b-it",
            "gemma-4-31b-it",
        ],
        credential_env_vars=["GEMINI_API_KEY"],
        supports_streaming=True,
        supports_native_tools=True,
        supports_vision=True,
        supports_audio=True,
        supports_thinking=True,
    ),
    "digitalocean": ProviderSpec(
        id="digitalocean",
        display_name="DigitalOcean Gradient",
        tier=1,
        default_model="llama3.3-70b-instruct",
        models=[
            "llama3.3-70b-instruct",
            "kimi-k3",
            "kimi-k2.6",
            "kimi-k2.5",
            "glm-5.3",
            "glm-5.3-flash",
            "glm-5.2",
            "glm-5.1",
            "glm-5",
            "deepseek-v4-pro",
            "deepseek-v4-flash-0731",
            "deepseek-4-flash",
            "deepseek-3.2",
            "qwen3.8-max",
            "qwen3.5-397b-a17b",
            "llama-4-maverick",
            "minimax-m2.5",
            "mimo-v2.5-pro",
            "nemotron-3-ultra-550b",
            "nemotron-3-nano-omni",
            "nemotron-nano-12b-v2-vl",
            "mistral-3-14B",
        ],
        credential_env_vars=["DO_MODEL_ACCESS_KEY"],
        supports_streaming=True,
        supports_native_tools=False,
        supports_vision=False,
        supports_audio=False,
        supports_thinking=False,
    ),
    "anthropic": ProviderSpec(
        id="anthropic",
        display_name="Anthropic Claude",
        tier=1,
        default_model=getattr(settings, "ANTHROPIC_DEFAULT_MODEL", "claude-sonnet-4-5") or "claude-sonnet-4-5",
        models=[
            "claude-sonnet-4-5",
            "claude-opus-4-5",
            "claude-haiku-4-5",
            "claude-3-7-sonnet-latest",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
            "claude-3-opus-latest",
        ],
        credential_env_vars=["ANTHROPIC_API_KEY"],
        supports_streaming=True,
        supports_native_tools=True,
        supports_vision=True,
        supports_audio=False,
        supports_thinking=True,
    ),
    "qwen": ProviderSpec(
        id="qwen",
        display_name="Alibaba Qwen",
        tier=1,
        default_model=getattr(settings, "QWEN_DEFAULT_MODEL", "qwen-turbo") or "qwen-turbo",
        models=[
            "qwen-turbo",
            "qwen-plus",
            "qwen-max",
            "qwen-long",
            "qwen3.8-flash",
            "qwen2.5-72b-instruct",
            "qwen2.5-32b-instruct",
            "qwen2.5-14b-instruct",
            "qwen2.5-7b-instruct",
            "qwen2.5-coder-32b-instruct",
            "qwen2.5-coder-7b-instruct",
            "qwen-vl-max",
            "qwen-vl-plus",
        ],
        credential_env_vars=["QWEN_API_KEY", "QWEN_BASE_URL"],
        supports_streaming=True,
        supports_native_tools=True,
        supports_vision=False,  # default False; vision-enabled on *-vl* models via capabilities
        supports_audio=False,
        supports_thinking=True,
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        display_name="DeepSeek",
        tier=1,
        default_model=getattr(settings, "DEEPSEEK_DEFAULT_MODEL", "deepseek-chat") or "deepseek-chat",
        models=[
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-coder",
        ],
        credential_env_vars=["DEEPSEEK_API_KEY"],
        supports_streaming=True,
        supports_native_tools=True,
        supports_vision=False,
        supports_audio=False,
        supports_thinking=True,
    ),
    "ollama": ProviderSpec(
        id="ollama",
        display_name="Local VPS (Ollama)",
        tier=2,
        default_model="qwen3.5:4b",
        models=[
            "qwen3.5:4b",
            "llama3.2",
            "mistral",
            "deepseek-r1",
            "phi3",
        ],
        credential_env_vars=["OLLAMA_BASE_URL"],
        supports_streaming=True,
        supports_native_tools=False,
        supports_vision=False,
        supports_audio=False,
        supports_thinking=False,
    ),
    "kaggle": ProviderSpec(
        id="kaggle",
        display_name="Batch GPU (Kaggle)",
        tier=3,
        default_model="qwen3.5-t4",
        models=[
            "qwen3.5-t4",
        ],
        credential_env_vars=["KAGGLE_TUNNEL_URL"],
        supports_streaming=True,
        supports_native_tools=False,
        supports_vision=False,
        supports_audio=False,
        supports_thinking=False,
    ),
}

# Provider to Tier mapping rules (Server-side enforced)
VALID_TIER_PROVIDERS: Dict[int, List[str]] = {
    1: ["gemini", "digitalocean", "anthropic", "qwen", "deepseek"],
    2: ["ollama"],
    3: ["kaggle"],
}


def normalize_provider_id(raw_provider: str) -> str:
    """Normalizes various user/client provider strings to canonical ID."""
    p = raw_provider.lower().strip()
    if p in ["google", "gemini", "google ai studio", "gemma"]:
        return "gemini"
    if p in ["do", "digitalocean", "gradient"]:
        return "digitalocean"
    if p in ["anthropic", "claude"]:
        return "anthropic"
    if p in ["qwen", "alibaba", "alibaba qwen", "dashscope"]:
        return "qwen"
    if p in ["deepseek", "deep seek"]:
        return "deepseek"
    if p in ["ollama", "local", "vps"]:
        return "ollama"
    if p in ["kaggle", "batch gpu", "kaggle t4"]:
        return "kaggle"
    return p


def get_provider(provider_id: str) -> Optional[ProviderSpec]:
    """Retrieves ProviderSpec by canonical or normalized ID."""
    clean_id = normalize_provider_id(provider_id)
    return PROVIDERS.get(clean_id)


def list_providers() -> List[ProviderSpec]:
    """Returns all registered providers."""
    return list(PROVIDERS.values())


def get_models_for_provider(provider_id: str) -> List[str]:
    """Returns list of supported models for the provider."""
    spec = get_provider(provider_id)
    return list(spec.models) if spec else []


def validate_provider_tier(provider_id: str, tier: int) -> bool:
    """Validates that provider_id belongs to the specified tier."""
    clean_id = normalize_provider_id(provider_id)
    allowed = VALID_TIER_PROVIDERS.get(tier, [])
    return clean_id in allowed


def validate_provider_credentials(provider_id: str) -> Tuple[bool, Optional[str]]:
    """Validates that credentials required for this provider are configured in settings."""
    clean_id = normalize_provider_id(provider_id)
    if clean_id not in PROVIDERS:
        return False, f"Unknown provider: '{provider_id}'."

    if clean_id == "gemini":
        if not settings.GEMINI_API_KEY:
            return False, "Google Gemini API key (GEMINI_API_KEY) is not configured in environment."
    elif clean_id == "digitalocean":
        if not settings.DO_MODEL_ACCESS_KEY:
            return False, "DigitalOcean Gradient Access Key (DO_MODEL_ACCESS_KEY) is not configured in environment."
    elif clean_id == "anthropic":
        if not getattr(settings, "ANTHROPIC_API_KEY", ""):
            return False, "Anthropic API key (ANTHROPIC_API_KEY) is not configured. Add it to .env to use Claude models."
    elif clean_id == "qwen":
        key = getattr(settings, "QWEN_API_KEY", "")
        base_url = getattr(settings, "QWEN_BASE_URL", "")
        if not key:
            return False, "Alibaba Qwen API key (QWEN_API_KEY) is not configured in .env."
        if not base_url:
            return False, "Alibaba Qwen Base URL (QWEN_BASE_URL) is not configured in .env."
    elif clean_id == "deepseek":
        if not getattr(settings, "DEEPSEEK_API_KEY", ""):
            return False, "DeepSeek API key (DEEPSEEK_API_KEY) is not configured in .env."
    elif clean_id == "ollama":
        if not getattr(settings, "OLLAMA_BASE_URL", ""):
            return False, "Ollama Base URL (OLLAMA_BASE_URL) is not configured."
    elif clean_id == "kaggle":
        if not getattr(settings, "KAGGLE_TUNNEL_URL", ""):
            return False, "Kaggle Tunnel URL (KAGGLE_TUNNEL_URL) is not configured."

    return True, None
