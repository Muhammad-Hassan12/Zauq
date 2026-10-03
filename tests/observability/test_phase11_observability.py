"""Unit tests for Phase 11: Observability, Cost Controls, and VPS Protection.

Verifies:
1. Extended request metrics tracking and metadata-driven cost estimation.
2. Metrics summary aggregation with cache statistics.
3. ToolExecutor structured logs with execution IDs (agent_run_id, tool_call_id).
4. Concurrency semaphores (web fetch, sandbox, MCP calls).
5. MCP retry storm protection (exponential backoff & failure breaker).
6. Agent runtime token extraction and telemetry propagation.
7. Orchestrator request_id propagation and structured request logging.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.config import settings
from backend.memory.metrics import (
    log_request_metric,
    get_metrics_summary,
    estimate_provider_cost,
    IN_MEMORY_LOGS,
)
from backend.search.cache import search_cache
from backend.tools.base import ToolSpec, ToolResult
from backend.tools.registry import ToolRegistry
from backend.tools.policy import ToolPolicy
from backend.tools.executor import ToolExecutor
from backend.mcp_client.manager import (
    ServerConnection,
    MCPManager,
    _get_mcp_call_semaphore,
)
from backend.mcp_client.models import MCPServerConfig
from backend.sandbox.code_runner import _get_semaphore as get_sandbox_semaphore
from backend.search.fetcher import _get_semaphore as get_fetch_semaphore
from backend.agent.runtime import AgentRuntime, AgentRunResult, extract_turn_usage
from backend.agent.types import AgentModelTurn, ToolCall


def test_estimate_provider_cost():
    """Verify cost calculation across different model pricing tiers."""
    # Gemini pricing: 0.075 / 1M in, 0.30 / 1M out
    cost = estimate_provider_cost("gemini", "gemini-2.5-flash", 1_000_000, 1_000_000)
    assert cost == 0.375

    # Anthropic pricing: 3.00 / 1M in, 15.00 / 1M out
    anthropic_cost = estimate_provider_cost("anthropic", "claude-sonnet-4-5", 100_000, 10_000)
    assert anthropic_cost == 0.45

    # Zero tokens returns None
    assert estimate_provider_cost("gemini", "gemini-2.5-flash", None, None) is None


@pytest.mark.asyncio
async def test_log_request_metric_records_all_fields_and_computes_cost():
    """Verify that log_request_metric records full Phase 11 telemetry."""
    IN_MEMORY_LOGS.clear()

    await log_request_metric(
        guild_id="guild_999",
        channel_id="chan_123",
        user_id="user_456",
        tier=1,
        provider="gemini",
        model_name="gemini-2.5-flash",
        response_time_ms=540,
        tool_steps=3,
        search_calls=1,
        pages_fetched=2,
        sandbox_calls=1,
        mcp_calls=1,
        tool_failures=0,
        agent_duration_ms=520,
        input_tokens=2000,
        output_tokens=500,
        request_id="req_test_001",
        agent_run_id="run_test_001",
    )

    assert len(IN_MEMORY_LOGS) == 1
    entry = IN_MEMORY_LOGS[0]
    assert entry["guild_id"] == "guild_999"
    assert entry["tool_steps"] == 3
    assert entry["search_calls"] == 1
    assert entry["pages_fetched"] == 2
    assert entry["sandbox_calls"] == 1
    assert entry["mcp_calls"] == 1
    assert entry["tool_failures"] == 0
    assert entry["request_id"] == "req_test_001"
    assert entry["agent_run_id"] == "run_test_001"
    assert entry["input_tokens"] == 2000
    assert entry["output_tokens"] == 500
    assert entry["estimated_provider_cost"] is not None
    assert entry["estimated_provider_cost"] > 0

    # Ensure no secret / prompt exposure
    assert "prompt" not in entry
    assert "content" not in entry


@pytest.mark.asyncio
async def test_get_metrics_summary_aggregates_telemetry_and_cache():
    """Verify that get_metrics_summary aggregates v4 telemetry and cache stats."""
    IN_MEMORY_LOGS.clear()

    await log_request_metric(
        guild_id="guild_summary",
        channel_id="c1",
        user_id="u1",
        tier=1,
        provider="gemini",
        model_name="gemini-2.5-flash",
        response_time_ms=100,
        tool_steps=2,
        search_calls=1,
        pages_fetched=1,
        sandbox_calls=0,
        mcp_calls=0,
        tool_failures=0,
        input_tokens=100,
        output_tokens=50,
    )
    await log_request_metric(
        guild_id="guild_summary",
        channel_id="c2",
        user_id="u2",
        tier=1,
        provider="anthropic",
        model_name="claude-sonnet-4-5",
        response_time_ms=200,
        tool_steps=3,
        search_calls=0,
        pages_fetched=0,
        sandbox_calls=1,
        mcp_calls=1,
        tool_failures=1,
        input_tokens=200,
        output_tokens=100,
    )

    summary = await get_metrics_summary("guild_summary")
    assert summary["total_requests"] == 2
    assert summary["avg_latency_ms"] == 150.0
    assert summary["total_tool_steps"] == 5
    assert summary["total_search_calls"] == 1
    assert summary["total_pages_fetched"] == 1
    assert summary["total_sandbox_calls"] == 1
    assert summary["total_mcp_calls"] == 1
    assert summary["total_tool_failures"] == 1
    assert summary["total_input_tokens"] == 300
    assert summary["total_output_tokens"] == 150
    assert summary["total_estimated_cost_usd"] > 0
    assert "cache_stats" in summary
    assert "hits" in summary["cache_stats"]
    assert "misses" in summary["cache_stats"]


@pytest.mark.asyncio
async def test_tool_executor_structured_logging_with_ids(caplog):
    """Verify structured log output format: agent_run=abc tool=name status=ok duration=...ms."""
    registry = ToolRegistry()
    policy = ToolPolicy()
    executor = ToolExecutor(registry=registry, policy=policy)

    spec = ToolSpec(
        name="test.ping",
        description="Ping tool",
        input_schema={"type": "object"},
        source="native",
        risk="read",
        timeout_seconds=5.0,
    )

    async def _ping_handler(args):
        return {"pong": True}

    registry.register(spec, _ping_handler)

    with caplog.at_level("INFO", logger="zauq.tools.executor"):
        res = await executor.execute(
            "test.ping",
            {},
            agent_run_id="run_xyz123",
            tool_call_id="call_abc456",
        )
        assert res.success is True
        log_text = caplog.text
        assert "agent_run=run_xyz123" in log_text
        assert "tool_call_id=call_abc456" in log_text
        assert "tool=test.ping" in log_text
        assert "status=ok" in log_text
        assert "duration=" in log_text


def test_concurrency_semaphores_bounded():
    """Verify concurrency semaphores respect configured values for VPS protection."""
    # Web fetch semaphore
    fetch_sem = get_fetch_semaphore()
    assert fetch_sem._value <= getattr(settings, "WEB_FETCH_CONCURRENCY", 3)

    # Sandbox semaphore
    sandbox_sem = get_sandbox_semaphore()
    assert sandbox_sem._value <= max(1, settings.SANDBOX_MAX_CONCURRENCY)

    # MCP call semaphore
    mcp_sem = _get_mcp_call_semaphore()
    assert mcp_sem._value <= getattr(settings, "MCP_MAX_CONCURRENCY", 4)


@pytest.mark.asyncio
async def test_mcp_server_retry_storm_prevention():
    """Verify failed MCP server pauses reconnection after max consecutive failures."""
    cfg = MCPServerConfig(
        id="broken_server",
        command="non_existent_binary",
        transport="stdio",
        enabled=True,
    )
    conn = ServerConnection(config=cfg)
    mgr = MCPManager()
    mgr._running = True
    mgr.connections[cfg.id] = conn

    # Simulate 5 consecutive connection failures
    for i in range(5):
        await mgr._connect_server(conn)

    assert conn.consecutive_failures == 5
    # Should not have active reconnect task after reaching max failures
    assert conn._reconnect_task is None or conn._reconnect_task.done()

    # Operator refresh resets failure count
    await mgr.refresh_server("broken_server")
    # Reset back to 1 (failed again on manual refresh, but circuit reset allowed the attempt)
    assert conn.consecutive_failures == 1


def test_extract_turn_usage_gemini_and_openai():
    """Verify token usage extraction from different provider metadata formats."""
    # Gemini format
    gemini_meta = {
        "usageMetadata": {
            "promptTokenCount": 250,
            "candidatesTokenCount": 80,
        }
    }
    in_t, out_t = extract_turn_usage(gemini_meta)
    assert in_t == 250
    assert out_t == 80

    # OpenAI / Anthropic format
    openai_meta = {
        "usage": {
            "prompt_tokens": 150,
            "completion_tokens": 60,
        }
    }
    in_t2, out_t2 = extract_turn_usage(openai_meta)
    assert in_t2 == 150
    assert out_t2 == 60


@pytest.mark.asyncio
async def test_agent_runtime_telemetry_propagation():
    """Verify AgentRuntime accurately records token counts and execution IDs in AgentRunResult."""
    mock_router = MagicMock()
    mock_executor = MagicMock()

    turn1 = AgentModelTurn(
        text=None,
        tool_calls=[ToolCall(id="call_1", name="web.search", arguments={"query": "test"})],
        raw_metadata={"usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20}},
    )
    turn2 = AgentModelTurn(
        text="Final answer based on search.",
        tool_calls=[],
        raw_metadata={"usageMetadata": {"promptTokenCount": 150, "candidatesTokenCount": 50}},
    )

    mock_router.generate_agent_turn = AsyncMock(side_effect=[turn1, turn2])
    mock_executor.execute = AsyncMock(
        return_value=ToolResult(
            tool_name="web.search",
            success=True,
            content={"results": []},
            duration_ms=120,
        )
    )

    spec = ToolSpec(name="web.search", description="Search", input_schema={}, source="native", risk="read")
    runtime = AgentRuntime(router=mock_router, executor=mock_executor)

    res = await runtime.run(
        messages=[{"role": "user", "content": "search something"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        system_prompt="Test system",
        tools=[spec],
    )

    assert res.final_response == "Final answer based on search."
    assert res.tool_steps == 1
    assert res.search_calls == 1
    assert res.input_tokens == 250   # 100 + 150
    assert res.output_tokens == 70   # 20 + 50
    assert res.agent_run_id is not None
    assert res.agent_run_id.startswith("run_")
    assert res.duration_ms >= 0
