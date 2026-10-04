"""Secret Sanitizer for Zauq v4.

Guarantees that sensitive environment variables, API keys, tokens, and credentials
are scrubbed and never leaked to LLM context, tool traces, or Discord responses.
"""

from __future__ import annotations
import os
import re
from typing import Any, Set

from backend.config import settings

# Generic regex patterns for common API keys and tokens
_SECRET_PATTERNS = [
    # Google AI Studio / Gemini API keys (starts with AIzaSy)
    re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"),
    # OpenAI, Anthropic, DeepSeek, and generic sk- keys
    re.compile(r"sk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    # GitHub personal access and fine-grained tokens
    re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}"),
    # Supabase / JWT tokens
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    # Bearer tokens (captures the token itself)
    re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9\-._~+/]+=*"),
]

# Sensitive dictionary keys that should always have their values redacted
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|auth|authorization|private[_-]?key)"
)

_REPLACEMENT = "[REDACTED_SECRET]"


def _get_configured_secrets() -> Set[str]:
    """Collect all non-empty active secret values from settings and environment."""
    secrets = set()

    # Settings fields known to hold secrets
    known_fields = [
        "SERPER_API_KEY",
        "GEMINI_API_KEY",
        "SUPABASE_KEY",
        "DO_MODEL_ACCESS_KEY",
        "INTERNAL_API_KEY",
        "DISCORD_BOT_TOKEN",
        "ANTHROPIC_API_KEY",
        "QWEN_API_KEY",
        "DEEPSEEK_API_KEY",
    ]

    for field in known_fields:
        val = getattr(settings, field, None)
        if val and isinstance(val, str) and len(val.strip()) >= 6:
            secrets.add(val.strip())

    # Environment variables with sensitive names
    for env_name, env_val in os.environ.items():
        if _SENSITIVE_KEY_PATTERN.search(env_name):
            if env_val and len(env_val.strip()) >= 6:
                secrets.add(env_val.strip())

    return secrets


def sanitize_secrets(text: str) -> str:
    """Scrub known secrets and standard token formats from string content.

    Returns the sanitized string with sensitive data replaced by [REDACTED_SECRET].
    """
    if not text or not isinstance(text, str):
        return text

    sanitized = text

    # 1. Exact string matches of configured secrets
    active_secrets = sorted(_get_configured_secrets(), key=len, reverse=True)
    for sec in active_secrets:
        if sec in sanitized:
            sanitized = sanitized.replace(sec, _REPLACEMENT)

    # 2. Pattern-based redaction for token formats
    # Bearer token regex replacement
    sanitized = re.sub(r"(?i)\b(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", rf"\g<1>{_REPLACEMENT}", sanitized)

    # Other secret patterns
    for pat in _SECRET_PATTERNS:
        if pat.pattern.startswith("(?i)\\b(Bearer"):
            continue
        sanitized = pat.sub(_REPLACEMENT, sanitized)

    return sanitized


def sanitize_object(data: Any) -> Any:
    """Recursively scrub secrets from nested dicts, lists, and primitives."""
    if isinstance(data, str):
        return sanitize_secrets(data)
    elif isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for k, v in data.items():
            if _SENSITIVE_KEY_PATTERN.search(str(k)):
                cleaned[k] = _REPLACEMENT
            else:
                cleaned[k] = sanitize_object(v)
        return cleaned
    elif isinstance(data, list):
        return [sanitize_object(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(sanitize_object(item) for item in data)
    elif isinstance(data, set):
        return {sanitize_object(item) for item in data}
    return data
