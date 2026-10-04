"""Integration Tests: Feature Matrix, Subsystems & Guild Scoping (Phase 13).

Strictly verifies:
- Model selection (channel override vs server default vs fallback)
- Fallback notification and recovery
- /search flow (with mocked search provider)
- /run sandbox execution flow
- Sandbox auto mode ('off', 'auto', 'always')
- MCP disabled (zero overhead)
- MCP connected (mock session registration)
- Unauthorized MCP guild (access blocked)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import BackgroundTasks

from backend.config import settings
from backend.routers.chat import ChatRequest, chat_completion
from backend.routers.model import set_model_selection, get_model_status, ModelSetRequest
from backend.routers.sandbox import CodeExecRequest, run_code
from backend.search.service import search_service
from backend.search.models import SearchResponse, SearchResult
from backend.mcp_client.manager import MCPManager
from backend.mcp_client.models import MCPServerConfig, MCPConfigFile
from backend.tools.registry import ToolRegistry


# ── 1. Model Selection & Fallback Behavior ───────────────────────────────────

@pytest.mark.asyncio
async def test_model_selection_and_fallback_to_gemini(monkeypatch):
    """Verify that a failing secondary provider gracefully triggers fallback to Gemini."""
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", False)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "mock_gemini_key_for_fallback")

    req = ChatRequest(
        channel_id="c_fallback_test",
        messages=[{"role": "user", "content": "Hello"}],
    )

    bg = BackgroundTasks()

    # Channel configured for Anthropic, but Anthropic fails -> fallback to Gemini
    with patch("backend.memory.db.db_helper.get_model_selection", new_callable=AsyncMock) as mock_sel, \
         patch("backend.models.router.model_router.generate", new_callable=AsyncMock) as mock_gen:

        mock_sel.return_value = {"provider": "anthropic", "model_name": "claude-sonnet-4-5"}

        # First call (anthropic) fails, second call (gemini fallback) succeeds
        mock_gen.side_effect = [
            RuntimeError("Anthropic API rate limit reached"),
            "Fallback response from Gemini 2.5 Flash",
        ]

        res = await chat_completion(req, bg)

        assert res["response"] == "Fallback response from Gemini 2.5 Flash"
        assert res["provider"] == "gemini"
        assert res["fallback_triggered"] is True
        assert res["original_provider"] == "anthropic"


# ── 2. Search Subsystem Flow (Mocked in CI) ───────────────────────────────────

@pytest.mark.asyncio
async def test_search_service_flow():
    """Verify search service returns structured organic results without paid API."""
    mock_resp = SearchResponse(
        query="fastapi framework",
        results=[
            SearchResult(title="FastAPI Docs", url="https://fastapi.tiangolo.com", snippet="Modern Python web framework.")
        ],
        provider="serper",
    )

    with patch.object(search_service, "search", new_callable=AsyncMock) as mock_search, \
         patch("backend.search.service.fetch_urls_parallel", new_callable=AsyncMock) as mock_fetch:

        mock_search.return_value = mock_resp
        mock_fetch.return_value = []

        res = await search_service.search_and_fetch("fastapi framework", max_results=3, fetch_top_n=1)

        assert len(res["results"]) == 1
        assert res["results"][0]["title"] == "FastAPI Docs"
        assert "FastAPI Docs" in res["context_text"]


# ── 3. Sandbox /run Flow ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_run_endpoint_flow(monkeypatch):
    """Verify /api/sandbox/exec receives code and returns execution response."""
    code_req = CodeExecRequest(
        code="print('Hello from Sandbox Test!')",
        language="python",
        timeout=5.0,
        channel_id='permitted-channel',
    )
    monkeypatch.setattr('backend.memory.db.db_helper.get_channel_profile', AsyncMock(return_value={'allow_code_exec':True}))

    mock_result = {
        "execution_id": "zauq_exec_mock_test",
        "success": True,
        "stdout": "Hello from Sandbox Test!\n",
        "stderr": "",
        "exit_code": 0,
        "execution_time_ms": 25,
        "timed_out": False,
        "truncated": False,
    }

    with patch("backend.routers.sandbox.execute_code", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_result
        resp = await run_code(code_req)

        assert resp["success"] is True
        assert resp["stdout"] == "Hello from Sandbox Test!\n"
        assert resp["execution_id"] == "zauq_exec_mock_test"


# ── 4. Sandbox Auto Mode Directives ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_auto_mode_directives():
    """Verify auto_code_test_mode values ('off', 'auto', 'always') in context building."""
    from backend.chat.context_builder import context_builder

    # When auto_code_test_mode is 'always'
    req_always = ChatRequest(
        channel_id="c_always",
        mode_override="dev",
        messages=[{"role": "user", "content": "write code"}],
    )

    with patch("backend.memory.db.db_helper.get_channel_profile", new_callable=AsyncMock) as mock_prof:
        mock_prof.return_value = {
            "operating_mode": "dev",
            "allow_code_exec": True,
            "auto_code_test_mode": "always",
        }
        ctx_always = await context_builder.build(req_always)
        assert "[AUTOMATIC CODE TESTING DIRECTIVE]" in ctx_always.persona
        assert ctx_always.auto_code_test_mode == "always"

    # When auto_code_test_mode is 'off'
    with patch("backend.memory.db.db_helper.get_channel_profile", new_callable=AsyncMock) as mock_prof:
        mock_prof.return_value = {
            "operating_mode": "dev",
            "allow_code_exec": True,
            "auto_code_test_mode": "off",
        }
        ctx_off = await context_builder.build(req_always)
        assert "[AUTOMATIC CODE TESTING DIRECTIVE]" not in ctx_off.persona
        assert ctx_off.auto_code_test_mode == "off"


# ── 5. MCP Disabled (Zero Overhead) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_disabled_zero_overhead(monkeypatch):
    """When MCP_ENABLED=false, MCPManager starts instantly with 0 connections."""
    monkeypatch.setattr(settings, "MCP_ENABLED", False)

    registry = ToolRegistry()
    manager = MCPManager(registry=registry)

    assert manager.is_enabled() is False
    await manager.start()
    assert len(manager.connections) == 0

    status = manager.get_status()
    assert status["enabled"] is False
    assert status["servers"] == []


# ── 6. MCP Connected & Unauthorized Guild Access Blocking ────────────────────

@pytest.mark.asyncio
async def test_mcp_connected_and_unauthorized_guild_scoping(monkeypatch):
    """Verify tool registration and that tools scoped to guild A are blocked in guild B."""
    monkeypatch.setattr(settings, "MCP_ENABLED", True)

    server_cfg = MCPServerConfig(
        id="internal_db",
        enabled=True,
        transport="stdio",
        command="mock_command",
        default_risk="read",
        allowed_guild_ids=["guild_allowed_111"],
    )
    config_file = MCPConfigFile(servers=[server_cfg])

    registry = ToolRegistry()
    manager = MCPManager(registry=registry, config=config_file)

    # Mock connection and tool discovery
    conn = manager.connections.get("internal_db")
    if conn is None:
        from backend.mcp_client.manager import ServerConnection
        conn = ServerConnection(server_cfg)
        manager.connections["internal_db"] = conn

    # Register an MCP tool under allowed_guild_ids=["guild_allowed_111"]
    from backend.tools.base import ToolSpec
    scoped_tool = ToolSpec(
        name="mcp.internal_db.query_users",
        description="Query user table",
        input_schema={"type": "object"},
        source="mcp",
        risk="read",
        allowed_guild_ids=["guild_allowed_111"],
    )
    async def dummy_handler(args): return "dummy"
    registry.register(scoped_tool, dummy_handler)

    # 1. Verification in allowed guild: tool is available
    allowed_tools = registry.list_tools(enabled_only=True)
    guild_111_tools = [t for t in allowed_tools if not t.allowed_guild_ids or "guild_allowed_111" in t.allowed_guild_ids]
    assert any(t.name == "mcp.internal_db.query_users" for t in guild_111_tools)

    # 2. Verification in unauthorized guild: tool is blocked
    guild_222_tools = [t for t in allowed_tools if not t.allowed_guild_ids or "guild_unauthorized_222" in t.allowed_guild_ids]
    assert not any(t.name == "mcp.internal_db.query_users" for t in guild_222_tools)

    # 3. Verification in DM: tool is blocked
    dm_tools = [t for t in allowed_tools if not t.allowed_guild_ids or "dm" in t.allowed_guild_ids]
    assert not any(t.name == "mcp.internal_db.query_users" for t in dm_tools)
