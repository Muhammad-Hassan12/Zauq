"""Tests for Bounded Agent Runtime in Zauq v4.

Verifies:
1. Direct answer shortcut (0 tool steps when no tools provided)
2. Single-step tool execution (model requests tool, tool runs, model answers)
3. Duplicate call guard (loop detection stops duplicate tool calls)
4. Max tool step limits (stops at step cap and requests synthesis)
5. Tool failure handling (exceptions become structured observations without crashing)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.agent.runtime import AgentRuntime, AgentRunResult
from backend.agent.types import AgentModelTurn, ToolCall
from backend.tools.base import ToolSpec, ToolResult
from backend.tools.executor import ToolExecutor
from backend.models.router import ModelRouter


@pytest.fixture
def mock_spec() -> ToolSpec:
    return ToolSpec(
        name="web.search",
        description="Search web",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        risk="read",
    )


@pytest.mark.asyncio
async def test_runtime_direct_shortcut_when_no_tools():
    """When no tools are passed, runtime executes a single direct model call."""
    mock_router = MagicMock(spec=ModelRouter)
    mock_router.generate = AsyncMock(return_value="Direct answer from model")
    mock_executor = MagicMock(spec=ToolExecutor)

    runtime = AgentRuntime(router=mock_router, executor=mock_executor)

    res: AgentRunResult = await runtime.run(
        messages=[{"role": "user", "content": "Hello"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        system_prompt="You are Zauq",
        tools=[],
    )

    assert res.final_response == "Direct answer from model"
    assert res.tool_steps == 0
    assert res.model_turns == 1
    assert res.tool_trace == []
    mock_router.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_single_tool_execution(mock_spec: ToolSpec):
    """Model emits a tool call, executor runs it, and model produces the final answer."""
    mock_router = MagicMock(spec=ModelRouter)
    # Turn 1: model asks to call web.search
    # Turn 2: model sees search results and gives final text answer
    mock_router.generate_agent_turn = AsyncMock(
        side_effect=[
            AgentModelTurn(
                text=None,
                tool_calls=[ToolCall(id="call_123", name="web.search", arguments={"query": "python 3.12"})],
            ),
            AgentModelTurn(
                text="Python 3.12 was released with significant performance improvements.",
                tool_calls=[],
            ),
        ]
    )

    mock_executor = MagicMock(spec=ToolExecutor)
    mock_executor.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="web.search",
            success=True,
            content={"results": [{"title": "Python 3.12", "snippet": "Released Oct 2023"}]},
            duration_ms=45,
        )
    )

    runtime = AgentRuntime(router=mock_router, executor=mock_executor)

    res = await runtime.run(
        messages=[{"role": "user", "content": "Tell me about Python 3.12"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        system_prompt="You are Zauq",
        tools=[mock_spec],
    )

    assert "Python 3.12 was released" in res.final_response
    assert res.tool_steps == 1
    assert res.model_turns == 2
    assert len(res.tool_trace) == 1
    assert res.tool_trace[0]["tool"] == "web.search"
    assert res.tool_trace[0]["success"] is True
    assert res.tool_trace[0]["duration_ms"] == 45
    call_kwargs = mock_executor.execute.call_args[1]
    assert call_kwargs["tool_name"] == "web.search"
    assert call_kwargs["arguments"] == {"query": "python 3.12"}
    assert call_kwargs["allow_code_exec"] is False
    assert call_kwargs["tool_call_id"] == "call_123"
    assert "agent_run_id" in call_kwargs


@pytest.mark.asyncio
async def test_runtime_loop_detection_duplicate_calls(mock_spec: ToolSpec):
    """Repeated tool call with identical arguments is detected and blocked."""
    mock_router = MagicMock(spec=ModelRouter)
    # Turn 1: Call web.search("loop query")
    # Turn 2: Model repeats identical web.search("loop query")
    # Turn 3: Model receives duplicate error and gives final answer
    mock_router.generate_agent_turn = AsyncMock(
        side_effect=[
            AgentModelTurn(
                text=None,
                tool_calls=[ToolCall(id="c1", name="web.search", arguments={"query": "loop query"})],
            ),
            AgentModelTurn(
                text=None,
                tool_calls=[ToolCall(id="c2", name="web.search", arguments={"query": "loop query"})],
            ),
            AgentModelTurn(
                text="I noticed the repeated query, here is what I know so far.",
                tool_calls=[],
            ),
        ]
    )

    mock_executor = MagicMock(spec=ToolExecutor)
    mock_executor.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="web.search",
            success=True,
            content={"results": []},
            duration_ms=10,
        )
    )

    runtime = AgentRuntime(router=mock_router, executor=mock_executor)

    res = await runtime.run(
        messages=[{"role": "user", "content": "stuck"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        system_prompt="You are Zauq",
        tools=[mock_spec],
    )

    # Tool executor should only have been called ONCE; second identical call was blocked
    assert mock_executor.execute.await_count == 1
    assert res.loop_detected is True
    assert len(res.tool_trace) == 2
    assert res.tool_trace[1]["error"] == "duplicate_call_detected"
    assert res.tool_trace[1]["success"] is False


@pytest.mark.asyncio
async def test_runtime_stops_at_max_steps(mock_spec: ToolSpec):
    """Runtime strictly stops when max_steps is reached and triggers final synthesis."""
    mock_router = MagicMock(spec=ModelRouter)
    # Model endlessly attempts new tool calls
    mock_router.generate_agent_turn = AsyncMock(
        side_effect=[
            AgentModelTurn(
                text=None,
                tool_calls=[ToolCall(id=f"c{i}", name="web.search", arguments={"query": f"query_{i}"})],
            )
            for i in range(10)
        ]
    )
    mock_router.generate = AsyncMock(return_value="Final synthesized answer after reaching limit.")

    mock_executor = MagicMock(spec=ToolExecutor)
    mock_executor.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="web.search",
            success=True,
            content={"results": []},
            duration_ms=5,
        )
    )

    runtime = AgentRuntime(router=mock_router, executor=mock_executor)

    res = await runtime.run(
        messages=[{"role": "user", "content": "endless research"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        system_prompt="You are Zauq",
        tools=[mock_spec],
        max_steps=3,
    )

    assert res.tool_steps == 3
    assert res.budget_exhausted is True
    assert res.final_response == "Final synthesized answer after reaching limit."
    mock_router.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_graceful_tool_failure(mock_spec: ToolSpec):
    """Tool execution failure does not crash runtime and informs the model."""
    mock_router = MagicMock(spec=ModelRouter)
    mock_router.generate_agent_turn = AsyncMock(
        side_effect=[
            AgentModelTurn(
                text=None,
                tool_calls=[ToolCall(id="c_fail", name="web.search", arguments={"query": "test"})],
            ),
            AgentModelTurn(
                text="The search service is temporarily offline, but I can answer from my training data.",
                tool_calls=[],
            ),
        ]
    )

    mock_executor = MagicMock(spec=ToolExecutor)
    mock_executor.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="web.search",
            success=False,
            error="Connection refused: 503 Service Unavailable",
            duration_ms=12,
        )
    )

    runtime = AgentRuntime(router=mock_router, executor=mock_executor)

    res = await runtime.run(
        messages=[{"role": "user", "content": "search"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        system_prompt="You are Zauq",
        tools=[mock_spec],
    )

    assert "temporarily offline" in res.final_response
    assert res.tool_steps == 1
    assert len(res.tool_trace) == 1
    assert res.tool_trace[0]["success"] is False
    assert "503" in res.tool_trace[0]["error"]
