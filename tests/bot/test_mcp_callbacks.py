from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from bot.commands import mcp_slash


@pytest.mark.asyncio
async def test_status_callback_uses_backend_factory(monkeypatch):
    client=AsyncMock()
    response=MagicMock(status_code=200)
    response.json.return_value={'enabled':True,'servers':[]}
    client.get.return_value=response
    @asynccontextmanager
    async def factory(**kwargs):yield client
    monkeypatch.setattr(mcp_slash,'api_client',factory)
    interaction=SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))
    cog=mcp_slash.MCPSlash(MagicMock())
    await cog.mcp_status.callback(cog,interaction)
    client.get.assert_awaited_once()
    assert 'embed' in interaction.followup.send.call_args.kwargs
