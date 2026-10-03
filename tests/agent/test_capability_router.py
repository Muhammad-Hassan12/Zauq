"""Tests for CapabilityRouter in Zauq v4.

Verifies deterministic tool subset routing:
- Providers without tool capability get 0 tools.
- Pure chat requests get 0 tools (no LLM planning overhead).
- URLs route to web.fetch.
- Search queries route to web.search + web.fetch.
- Explicit flags (enable_web_search, deep_search) route to web tools.
- Code execution respects allow_code_exec policy.
"""

import pytest
from backend.agent.capability_router import CapabilityRouter
from backend.tools.base import ToolSpec
from backend.tools.registry import ToolRegistry


@pytest.fixture
def mock_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="web.search",
            description="Search the web",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            risk="read",
        ),
        lambda args: {"results": []},
    )
    reg.register(
        ToolSpec(
            name="web.fetch",
            description="Fetch a URL",
            input_schema={"type": "object", "properties": {"url": {"type": "string"}}},
            risk="read",
        ),
        lambda args: {"text": "hello"},
    )
    reg.register(
        ToolSpec(
            name="code.execute",
            description="Execute code",
            input_schema={"type": "object", "properties": {"code": {"type": "string"}}},
            risk="privileged",
        ),
        lambda args: {"stdout": "done"},
    )
    return reg


@pytest.fixture
def router(mock_registry: ToolRegistry) -> CapabilityRouter:
    return CapabilityRouter(registry=mock_registry)


def test_provider_lacking_tools_returns_empty(router: CapabilityRouter):
    """Kaggle and unsupported Ollama models return no tools."""
    tools = router.select_tools(
        messages=[{"role": "user", "content": "Search for Python 3.12 release notes"}],
        provider="kaggle",
        model_name="unsupported-model",
        enable_web_search=True,
    )
    assert tools == []


def test_conversational_query_returns_empty(router: CapabilityRouter):
    """General conversation does not attach any tools."""
    tools = router.select_tools(
        messages=[{"role": "user", "content": "Hello Zauq, tell me a short poem."}],
        provider="gemini",
        model_name="gemini-2.5-flash",
    )
    assert tools == []


def test_url_in_message_selects_web_fetch(router: CapabilityRouter):
    """URLs in message trigger web.fetch selection."""
    tools = router.select_tools(
        messages=[{"role": "user", "content": "Please read https://docs.python.org/3/whatsnew/3.12.html"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
    )
    names = [t.name for t in tools]
    assert "web.fetch" in names


def test_search_intent_selects_web_tools(router: CapabilityRouter):
    """Search queries trigger web.search and web.fetch."""
    tools = router.select_tools(
        messages=[{"role": "user", "content": "Who won the ICC cricket world cup 2024 final?"}],
        provider="anthropic",
        model_name="claude-sonnet-4-5",
    )
    names = [t.name for t in tools]
    assert "web.search" in names
    assert "web.fetch" in names


def test_explicit_search_flags_select_web_tools(router: CapabilityRouter):
    """Explicit enable_web_search or deep_search flags select web tools."""
    tools = router.select_tools(
        messages=[{"role": "user", "content": "General question"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        enable_web_search=True,
    )
    names = [t.name for t in tools]
    assert "web.search" in names
    assert "web.fetch" in names


def test_code_intent_respects_allow_code_exec(router: CapabilityRouter):
    """code.execute is only selected if allow_code_exec=True."""
    # When allow_code_exec is False
    tools_disabled = router.select_tools(
        messages=[{"role": "user", "content": "execute python code: print(2+2)"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        allow_code_exec=False,
        auto_code_test_mode="auto",
    )
    assert "code.execute" not in [t.name for t in tools_disabled]

    # When allow_code_exec is True
    tools_enabled = router.select_tools(
        messages=[{"role": "user", "content": "execute python code: print(2+2)"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        allow_code_exec=True,
        auto_code_test_mode="auto",
    )
    assert "code.execute" in [t.name for t in tools_enabled]
