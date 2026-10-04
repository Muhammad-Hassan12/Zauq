import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from backend.config import settings
from backend.mcp_client.manager import MCPManager, ServerConnection
from backend.mcp_client.models import MCPConfigFile, MCPServerConfig
from backend.mcp_client.adapter import mcp_tool_to_spec
from backend.tools.registry import ToolRegistry
from backend.tools.executor import ToolExecutor
from backend.tools.policy import ToolPolicy


def test_missing_scope_and_unknown_tool_are_denied():
    cfg=MCPServerConfig(id='private',allowed_tools=['read'],default_risk='read')
    spec=mcp_tool_to_spec({'name':'read'},cfg,AsyncMock())
    assert spec.allowed_guild_ids==[]
    assert ToolPolicy().evaluate(spec,guild_id='any').value=='deny'
    unknown=mcp_tool_to_spec({'name':'new_mutation'},cfg,AsyncMock())
    assert not unknown.enabled


@pytest.mark.asyncio
async def test_retries_reach_circuit_breaker_in_one_owner_task(monkeypatch):
    manager=MCPManager(registry=ToolRegistry())
    manager._running=True
    conn=ServerConnection(MCPServerConfig(id='fail',transport='stdio',command='missing',allowed_guild_ids=['guild']))
    conn._backoff_seconds=0.001
    async def fail(c):
        c.consecutive_failures+=1
        return False
    monkeypatch.setattr(manager,'_connect_once',fail)
    await manager._connect_server(conn)
    await asyncio.wait_for(conn._reconnect_task,1)
    assert conn.consecutive_failures==5
    assert not conn.status.connected


@pytest.mark.asyncio
async def test_actual_stdio_discovery_execution_and_owned_shutdown(monkeypatch):
    monkeypatch.setattr(settings,'MCP_ENABLED',True)
    path=Path(__file__).resolve().parent/'fixtures/echo_server.py'
    cfg=MCPServerConfig(id='local',transport='stdio',command=sys.executable,args=[str(path)],allowed_guild_ids=['guild'],allowed_tools=['echo'],default_risk='read')
    registry=ToolRegistry()
    manager=MCPManager(registry,MCPConfigFile(servers=[cfg]))
    try:
        await manager.start()
        assert manager.connections['local'].status.connected
        result=await ToolExecutor(registry,ToolPolicy()).execute('mcp.local.echo',{'value':'ok'},guild_id='guild')
        assert result.success and 'ok' in str(result.content)
    finally:
        await manager.stop()
    assert not len(registry)


@pytest.mark.asyncio
async def test_actual_http_discovery_execution_and_shutdown(monkeypatch):
    import socket
    import httpx
    monkeypatch.setattr(settings, 'MCP_ENABLED', True)
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    path = Path(__file__).resolve().parent/'fixtures/echo_server.py'
    proc = await asyncio.create_subprocess_exec(sys.executable,str(path),str(port),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
    registry = ToolRegistry()
    cfg = MCPServerConfig(id='http-local',transport='streamable_http',url=f'http://127.0.0.1:{port}/mcp',allowed_guild_ids=['guild'],allowed_tools=['echo'],default_risk='read')
    manager = MCPManager(registry,MCPConfigFile(servers=[cfg]))
    try:
        async with httpx.AsyncClient() as client:
            for _ in range(100):
                try:
                    await client.get(cfg.url)
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(.05)
            else:
                raise AssertionError('Local MCP HTTP fixture did not start')
        await manager.start()
        assert manager.connections[cfg.id].status.connected
        result = await ToolExecutor(registry,ToolPolicy()).execute('mcp.http-local.echo',{'value':'http-ok'},guild_id='guild')
        assert result.success and 'http-ok' in str(result.content)
    finally:
        await manager.stop()
        if proc.returncode is None:
            proc.terminate()
        await asyncio.wait_for(proc.wait(),5)
    assert len(registry) == 0
