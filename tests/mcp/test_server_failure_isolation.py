"""Tests for MCP server failure isolation, lifecycle, and zero-overhead behavior."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.mcp_client.manager import MCPManager, ServerConnection
from backend.mcp_client.models import MCPServerConfig, MCPConfigFile
from backend.tools.registry import ToolRegistry


class DummyTool:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.input_schema = {"type": "object"}


@pytest.mark.asyncio
async def test_mcp_disabled_zero_overhead(monkeypatch):
    monkeypatch.setattr("backend.config.settings.MCP_ENABLED", False)

    registry = ToolRegistry()
    mgr = MCPManager(registry=registry)

    # Calling start should immediately exit without touching network or config
    await mgr.start()
    assert mgr.is_enabled() is False
    assert len(mgr.connections) == 0

    status = mgr.get_status()
    assert status["enabled"] is False
    assert status["servers"] == []


@pytest.mark.asyncio
async def test_server_failure_isolation(monkeypatch):
    """Verify that when Server A fails to connect, Server B connects and works normally."""
    monkeypatch.setattr("backend.config.settings.MCP_ENABLED", True)

    registry = ToolRegistry()

    config = MCPConfigFile(
        servers=[
            MCPServerConfig(
                id="server_failing",
                transport="streamable_http",
                url="https://invalid-non-existent-host.fail/mcp",
                enabled=True,
            ),
            MCPServerConfig(
                id="server_working",
                transport="streamable_http",
                url="https://working-mcp-host.local/mcp",
                enabled=True,
                namespace_prefix="working",
            ),
        ]
    )

    mgr = MCPManager(registry=registry, config=config)

    # Mock _connect_server behavior: fail for server_failing, succeed for server_working
    async def mock_connect(conn: ServerConnection) -> bool:
        if conn.config.id == "server_failing":
            conn.status.connected = False
            conn.status.error = "Connection refused by host"
            return False
        else:
            conn.status.connected = True
            conn.status.tools = 1
            mock_session = AsyncMock()
            mock_session.list_tools = AsyncMock(
                return_value=MagicMock(tools=[DummyTool("ping", "Ping service")])
            )
            mock_session.call_tool = AsyncMock(return_value="pong")
            conn.session = mock_session
            await mgr._discover_and_register_tools(conn)
            return True

    with patch.object(mgr, "_connect_server", side_effect=mock_connect):
        await mgr.start()

    # Verify Server A failed safely
    status_a = mgr.connections["server_failing"].status
    assert status_a.connected is False
    assert "refused" in status_a.error

    # Verify Server B succeeded
    status_b = mgr.connections["server_working"].status
    assert status_b.connected is True
    assert status_b.tools == 1

    # Verify tool registry has Server B's tool but nothing from Server A
    assert "working.ping" in registry
    assert "mcp.server_failing.ping" not in registry

    # Status response format adheres strictly to specification
    full_status = mgr.get_status()
    assert full_status["enabled"] is True
    assert len(full_status["servers"]) == 2

    # Verify clean shutdown
    await mgr.stop()
    assert "working.ping" not in registry
    assert len(mgr.connections) == 0


@pytest.mark.asyncio
async def test_refresh_server(monkeypatch):
    monkeypatch.setattr("backend.config.settings.MCP_ENABLED", True)

    registry = ToolRegistry()
    config = MCPConfigFile(
        servers=[
            MCPServerConfig(
                id="test_srv",
                transport="streamable_http",
                url="https://test.mcp",
                enabled=True,
            )
        ]
    )

    mgr = MCPManager(registry=registry, config=config)
    conn = ServerConnection(config.servers[0])
    conn.status.connected = True
    mgr.connections["test_srv"] = conn

    # First discovery has tool1
    mock_session = AsyncMock()
    mock_session.list_tools = AsyncMock(
        return_value=MagicMock(tools=[DummyTool("tool1")])
    )
    conn.session = mock_session

    await mgr.refresh_server("test_srv")
    assert "mcp.test_srv.tool1" in registry

    # Refresh with tool2 replacing tool1
    mock_session.list_tools = AsyncMock(
        return_value=MagicMock(tools=[DummyTool("tool2")])
    )
    await mgr.refresh_server("test_srv")
    assert "mcp.test_srv.tool1" not in registry
    assert "mcp.test_srv.tool2" in registry
