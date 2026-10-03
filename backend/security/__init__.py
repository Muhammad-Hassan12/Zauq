"""Security and hardening utilities for Zauq v4.

Includes:
- Secret sanitization (prevent leaking API keys and tokens to LLM or Discord)
- Prompt injection protection directives and content fencing
- SSRF validation and URL safety checks
"""

from backend.security.sanitizer import sanitize_secrets, sanitize_object
from backend.security.prompt_guard import (
    PROMPT_INJECTION_DIRECTIVE,
    fence_tool_data,
    wrap_untrusted_content,
)
from backend.security.ssrf import is_safe_public_url, is_safe_ip_address

__all__ = [
    "sanitize_secrets",
    "sanitize_object",
    "PROMPT_INJECTION_DIRECTIVE",
    "fence_tool_data",
    "wrap_untrusted_content",
    "is_safe_public_url",
    "is_safe_ip_address",
]
