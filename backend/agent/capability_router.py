"""Capability Router for Zauq v4.

Determines the minimal, relevant tool subset for a request cheaply and deterministically
without spending paid LLM requests on autonomous planning.

Routing Rules:
- If model provider lacks FUNCTION_CALLING capability -> returns []
- URLs in messages or web browsing intent -> web.fetch (and web.search)
- Web search intent or explicit search request -> web.search, web.fetch
- Coding/execution intent (if allowed by channel policy) -> code.execute (when registered)
- GitHub / MCP intent (when connected) -> github.*
- Pure conversational / general reasoning -> [] (no tool overhead)
"""

from __future__ import annotations
import re
import logging
from typing import Any, List, Optional

from backend.tools.base import ToolSpec
from backend.tools.registry import ToolRegistry, tool_registry
from backend.models.capabilities import supports_native_tools
from backend.integrations.web_search import web_search_engine

logger = logging.getLogger("zauq.agent.capability_router")

_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

_CODE_EXEC_KEYWORDS = {
    "run python",
    "execute code",
    "run code",
    "run script",
    "test this code",
    "evaluate code",
    "execute python",
    "run this",
}

_GITHUB_KEYWORDS = {
    "github issue",
    "pull request",
    "create issue",
    "close issue",
    "github pr",
    "github repo",
    "commit history",
    "git commit",
}


class CapabilityRouter:
    """Routes requests to the minimal relevant tool subset deterministically."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry if registry is not None else tool_registry

    def has_urls(self, text: str) -> bool:
        """Check if text contains one or more HTTP/HTTPS URLs."""
        return bool(_URL_PATTERN.search(text))

    def has_search_intent(self, text: str) -> bool:
        """Check if text expresses search intent or requires current web knowledge."""
        if not text:
            return False
        return web_search_engine.should_search_web(text)

    def has_code_intent(self, text: str) -> bool:
        """Check if user explicitly asks to run/execute code."""
        lower = text.lower()
        return any(kw in lower for kw in _CODE_EXEC_KEYWORDS)

    def has_github_intent(self, text: str) -> bool:
        """Check if user asks for GitHub MCP interactions."""
        lower = text.lower()
        return any(kw in lower for kw in _GITHUB_KEYWORDS)

    def select_tools(
        self,
        messages: List[dict[str, Any]],
        provider: str,
        model_name: str,
        *,
        enable_web_search: Optional[bool] = None,
        deep_search: bool = False,
        search_query: Optional[str] = None,
        allow_code_exec: bool = False,
        auto_code_test_mode: str = "off",
        guild_id: Optional[str] = None,
    ) -> List[ToolSpec]:
        """Select the minimal, relevant tool subset for this request.

        Args:
            messages: Conversation history.
            provider: Target LLM provider (gemini, anthropic, qwen, deepseek, etc.).
            model_name: Specific model name.
            enable_web_search: Explicit search flag from client.
            deep_search: Deep search mode flag.
            search_query: Explicit search query string.
            allow_code_exec: Whether code execution is permitted by channel policy.
            auto_code_test_mode: 'off', 'auto', or 'always'.
            guild_id: Requesting Discord guild ID (for scoping MCP tools).

        Returns:
            List of ToolSpec instances for tools the model is permitted to call.
        """
        # 1. Verify that provider supports tool calling
        if not supports_native_tools(provider, model_name):
            logger.debug(f"Provider '{provider}' (model='{model_name}') lacks native tool support. Returning no tools.")
            return []

        # Ensure native tools are imported/registered
        try:
            import backend.tools.native.web_tools  # noqa: F401
            import backend.tools.native.code_tools  # noqa: F401
        except Exception as e:
            logger.warning(f"Failed to ensure native tools registration: {e}")

        # Extract latest user message
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = m.get("content", "")
                break

        selected_names: set[str] = set()

        # 2. Check explicit search flags
        if enable_web_search or deep_search or search_query:
            selected_names.add("web.search")
            selected_names.add("web.fetch")

        # 3. Check for URLs in messages
        if self.has_urls(user_text):
            selected_names.add("web.fetch")

        # 4. Check for implicit web search intent
        if self.has_search_intent(user_text):
            selected_names.add("web.search")
            selected_names.add("web.fetch")

        # 5. Check for code execution (Phase 5 policy: allow_code_exec=True AND auto_code_test_mode != 'off')
        if allow_code_exec and auto_code_test_mode != "off":
            if auto_code_test_mode == "always" or self.has_code_intent(user_text):
                if "code.execute" in self.registry:
                    selected_names.add("code.execute")

        # 6. Check for GitHub intent (MCP or native)
        if self.has_github_intent(user_text):
            for t in self.registry.list_tools(enabled_only=True):
                if t.name.startswith("github.") or t.name.startswith("mcp.github."):
                    selected_names.add(t.name)

        # 7. Collect ToolSpec objects from registry, enforcing guild scoping
        result: List[ToolSpec] = []
        for name in sorted(selected_names):
            spec = self.registry.get(name)
            if spec and spec.enabled:
                if spec.allowed_guild_ids:
                    if not guild_id or guild_id not in spec.allowed_guild_ids:
                        continue
                result.append(spec)

        logger.debug(
            f"CapabilityRouter selected {len(result)} tools for provider '{provider}': "
            f"{[t.name for t in result]}"
        )
        return result


# Global singleton
capability_router = CapabilityRouter()
