"""Capability Detection & Mapping for Zauq AI Models."""

from typing import Any, Dict, Optional
from backend.models.catalog import normalize_provider_id, get_provider


def supports_streaming(provider_id: str, model_name: Optional[str] = None) -> bool:
    """Returns True if the provider/model supports streaming responses."""
    spec = get_provider(provider_id)
    return spec.supports_streaming if spec else False


def supports_vision(provider_id: str, model_name: Optional[str] = None) -> bool:
    """Returns True if provider/model can accept image inputs natively.
    
    If False, Zauq routes attachments through Gemini Flash Vision fallback.
    """
    clean_id = normalize_provider_id(provider_id)
    m = (model_name or "").lower()

    if clean_id == "gemini":
        return not m.startswith("gemma")
    elif clean_id == "anthropic":
        return any(k in m for k in ["claude-3", "claude-sonnet", "claude-opus", "claude-haiku", "claude-4", "claude-5", "claude-fable"])
    elif clean_id == "qwen":
        return "vl" in m
    elif clean_id == "deepseek":
        return False
    elif clean_id == "ollama":
        return False
    elif clean_id in ["digitalocean", "kaggle"]:
        return False

    return False


def supports_audio(provider_id: str, model_name: Optional[str] = None) -> bool:
    """Returns True if provider/model natively ingests audio bytes.
    
    If False, Zauq transcribes audio attachments via Whisper first.
    """
    clean_id = normalize_provider_id(provider_id)
    m = (model_name or "").lower()
    if clean_id == "gemini":
        return "gemini-2" in m or "gemini-3" in m or not m
    return False


def supports_thinking(provider_id: str, model_name: Optional[str] = None) -> bool:
    """Returns True if provider/model supports native thinking / reasoning tokens."""
    clean_id = normalize_provider_id(provider_id)
    m = (model_name or "").lower()

    if clean_id == "gemini":
        return m.startswith(('gemini-2.5', 'gemini-3'))
    elif clean_id == "anthropic":
        return any(k in m for k in ["claude-3-7", "claude-sonnet-4-5", "claude-opus-4-5", "claude-sonnet-5", "claude-opus-5", "claude-fable"])
    elif clean_id == "deepseek":
        return m in ('deepseek-flash', 'deepseek-v4-pro', 'deepseek-v4-flash') or 'reasoner' in m or 'r1' in m
    elif clean_id == "qwen":
        return (m.startswith('qwen3') or 'qwq' in m) and 'instruct' not in m and 'omni' not in m
    elif clean_id == "ollama":
        return False

    return False


def supports_native_tools(provider_id: str, model_name: Optional[str] = None) -> bool:
    """Returns True if provider and model have verified native function/tool calling support."""
    clean_id = normalize_provider_id(provider_id)
    m = (model_name or "").lower()

    if clean_id == "gemini":
        return not m.startswith("gemma")
    elif clean_id == "anthropic":
        return any(k in m for k in ["claude-3", "claude-sonnet", "claude-opus", "claude-haiku", "claude-4", "claude-5", "claude-fable"]) or not m
    elif clean_id == "qwen":
        return any(k in m for k in ["turbo", "plus", "max", "qwen2.5", "qwen3", "qwq", "qwen-long"]) or not m
    elif clean_id == "deepseek":
        if 'reasoner' in m or m.endswith('-r1') or m == 'deepseek-r1':
            return False
        return m in ('deepseek-flash', 'deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-v3', 'deepseek-v3.2', 'deepseek-chat', 'deepseek-coder') or not m
    elif clean_id == "digitalocean":
        return m in ["llama3.3-70b-instruct"]
    elif clean_id in ["ollama", "kaggle"]:
        return False

    return False



def get_thinking_config(
    provider_id: str,
    model_name: Optional[str] = None,
    thinking_enabled: bool = False
) -> Dict[str, Any]:
    """Returns provider-specific parameter mapping for thinking mode.
    
    Ensures no hidden chain-of-thought prompt injection when native support exists.
    """
    if not thinking_enabled:
        return {}

    clean_id = normalize_provider_id(provider_id)
    m = (model_name or "").lower()

    if clean_id == "gemini":
        return {"thinking_budget": 2048}
    elif clean_id == "anthropic":
        if supports_thinking(clean_id, model_name):
            return {"type": "enabled", "budget_tokens": 2048}
        return {}
    elif clean_id == "deepseek":
        if "reasoner" in m:
            return {"reasoning": True}
        return {}
    elif clean_id == "qwen":
        if supports_thinking(clean_id, model_name):
            return {"enable_thinking": True}
        return {}

    return {}


def get_model_capabilities(provider_id: str, model_name: Optional[str] = None) -> Dict[str, bool]:
    """Aggregates all capabilities for the given provider and model."""
    return {
        "streaming": supports_streaming(provider_id, model_name),
        "vision": supports_vision(provider_id, model_name),
        "audio": supports_audio(provider_id, model_name),
        "thinking": supports_thinking(provider_id, model_name),
        "native_tools": supports_native_tools(provider_id, model_name),
    }
