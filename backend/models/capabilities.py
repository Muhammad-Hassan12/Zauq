"""Capability Detection & Mapping for Zauq AI Models.

Determines multimodal (vision/audio), streaming, thinking/reasoning mode,
and native tool-calling capabilities dynamically per provider and model.
"""

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
        # Gemma models are text-only; Gemini models are multimodal
        return not m.startswith("gemma")
    elif clean_id == "anthropic":
        # Claude 3, 3.5, 3.7, 4.5 Sonnet/Opus/Haiku support images
        return any(k in m for k in ["claude-3", "claude-sonnet", "claude-opus", "claude-haiku", "claude-4"])
    elif clean_id == "qwen":
        # Only Qwen-VL variants accept native images
        return "vl" in m
    elif clean_id == "deepseek":
        return "vl" in m
    elif clean_id == "ollama":
        return any(k in m for k in ["llava", "vision", "vl"])
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
        return True
    elif clean_id == "anthropic":
        return any(k in m for k in ["claude-3-7", "claude-sonnet-4-5", "claude-opus-4-5"])
    elif clean_id == "deepseek":
        return "reasoner" in m or "r1" in m
    elif clean_id == "qwen":
        return any(k in m for k in ["qwq", "qwen3.8-flash", "reasoning", "max"])
    elif clean_id == "ollama":
        return any(k in m for k in ["deepseek-r1", "qwq"])

    return False


def supports_native_tools(provider_id: str, model_name: Optional[str] = None) -> bool:
    """Returns True if provider and model have verified native function/tool calling support."""
    clean_id = normalize_provider_id(provider_id)
    m = (model_name or "").lower()

    if clean_id == "gemini":
        # Gemma models are open weights text-only; Gemini models support native tools
        return not m.startswith("gemma")
    elif clean_id == "anthropic":
        # Claude 3, 3.5, 3.7, 4.5 support native Claude tool use
        return any(k in m for k in ["claude-3", "claude-sonnet", "claude-opus", "claude-haiku", "claude-4"]) or not m
    elif clean_id == "qwen":
        # Verified models on Alibaba Cloud Model Studio: qwen-turbo, qwen-plus, qwen-max, qwen2.5-*
        return any(k in m for k in ["turbo", "plus", "max", "qwen2.5", "qwen-long"]) or not m
    elif clean_id == "deepseek":
        # Official DeepSeek-V3 (deepseek-chat) supports tools; deepseek-reasoner (R1) does not
        return "chat" in m or not m
    elif clean_id == "digitalocean":
        # Opt-in allowlist after verification per hosted model
        return m in ["llama3.3-70b-instruct"]
    elif clean_id in ["ollama", "kaggle"]:
        # Off by default until worker/model protocol is verified
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
