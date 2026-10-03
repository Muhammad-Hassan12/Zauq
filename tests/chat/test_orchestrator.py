"""Tests for ChatOrchestrator in Zauq.

Verifies:
1. Legacy v3 path when AGENT_RUNTIME_ENABLED=False
2. v4 Bounded Agent path when AGENT_RUNTIME_ENABLED=True
3. Graceful fallback to Gemini if secondary provider fails
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import BackgroundTasks

from backend.chat.orchestrator import ChatOrchestrator
from backend.chat.context_builder import ChatContext
from backend.agent.runtime import AgentRunResult
from backend.config import settings


@pytest.fixture
def mock_req():
    req = MagicMock()
    req.channel_id = "test-channel"
    req.guild_id = "test-guild"
    req.user_id = "user-123"
    req.user_name = "Hassan"
    req.mode_override = None
    req.attachments = None
    req.enable_web_search = None
    req.deep_search = False
    req.search_category = "all"
    req.search_query = None
    req.messages = [{"role": "user", "content": "What is Python?"}]
    return req


@pytest.fixture
def mock_context():
    return ChatContext(
        persona="You are Zauq Dev",
        mode="dev",
        temperature=0.2,
        provider="gemini",
        model_name="gemini-2.5-flash",
        enable_search=False,
        thinking_enabled=False,
        allow_code_exec=True,
        media_parts=[],
        working_messages=[{"role": "user", "content": "What is Python?"}],
    )


@pytest.mark.asyncio
async def test_orchestrator_legacy_path(mock_req, mock_context, monkeypatch):
    """When AGENT_RUNTIME_ENABLED is False, orchestrator runs legacy generate path."""
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", False)

    mock_cb = MagicMock()
    mock_cb.build = AsyncMock(return_value=mock_context)

    mock_router = MagicMock()
    mock_router.generate = AsyncMock(return_value="Python is a programming language.")

    orchestrator = ChatOrchestrator(context_builder_inst=mock_cb, router=mock_router)

    bg_tasks = MagicMock(spec=BackgroundTasks)
    res = await orchestrator.run(mock_req, bg_tasks)

    assert res["response"] == "Python is a programming language."
    assert res["provider"] == "gemini"
    assert res["mode"] == "dev"
    assert "tool_steps" not in res  # v3 legacy does not output tool_steps
    mock_router.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_agent_runtime_path(mock_req, mock_context, monkeypatch):
    """When AGENT_RUNTIME_ENABLED is True, orchestrator executes agent_runtime.run."""
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", True)

    mock_cb = MagicMock()
    mock_cb.build = AsyncMock(return_value=mock_context)

    mock_cap = MagicMock()
    mock_cap.select_tools = MagicMock(return_value=[])

    mock_runtime = MagicMock()
    mock_run_result = AgentRunResult(
        final_response="Python is versatile.",
        tool_trace=[{"tool": "web.search", "success": True, "duration_ms": 20}],
        tool_steps=1,
        model_turns=2,
    )
    mock_runtime.run = AsyncMock(return_value=mock_run_result)

    orchestrator = ChatOrchestrator(
        context_builder_inst=mock_cb,
        runtime=mock_runtime,
        cap_router=mock_cap,
    )

    bg_tasks = MagicMock(spec=BackgroundTasks)
    res = await orchestrator.run(mock_req, bg_tasks)

    assert res["response"] == "Python is versatile."
    assert res["tool_steps"] == 1
    assert len(res["tool_trace"]) == 1
    assert res["tool_trace"][0]["tool"] == "web.search"
    mock_runtime.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_orchestrator_fallback_to_gemini(mock_req, monkeypatch):
    """If secondary provider fails in agent mode, automatically falls back to Gemini 2.5 Flash."""
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", True)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock-gemini-key")

    context_anthropic = ChatContext(
        persona="You are Zauq",
        mode="hangout",
        temperature=0.7,
        provider="anthropic",
        model_name="claude-sonnet-4-5",
        enable_search=False,
        thinking_enabled=False,
        allow_code_exec=False,
        media_parts=[],
        working_messages=[{"role": "user", "content": "Help me"}],
    )

    mock_cb = MagicMock()
    mock_cb.build = AsyncMock(return_value=context_anthropic)

    mock_cap = MagicMock()
    mock_cap.select_tools = MagicMock(return_value=[])

    mock_runtime = MagicMock()
    mock_run_fallback = AgentRunResult(
        final_response="Fallback response from Gemini Flash.",
        tool_trace=[],
        tool_steps=0,
        model_turns=1,
    )
    mock_runtime.run = AsyncMock(
        side_effect=[
            RuntimeError("Anthropic API credit limit reached"),
            mock_run_fallback,
        ]
    )

    orchestrator = ChatOrchestrator(
        context_builder_inst=mock_cb,
        runtime=mock_runtime,
        cap_router=mock_cap,
    )

    bg_tasks = MagicMock(spec=BackgroundTasks)
    res = await orchestrator.run(mock_req, bg_tasks)

    assert res["fallback_triggered"] is True
    assert res["original_provider"] == "anthropic"
    assert res["provider"] == "gemini"
    assert res["response"] == "Fallback response from Gemini Flash."
    assert mock_runtime.run.await_count == 2
