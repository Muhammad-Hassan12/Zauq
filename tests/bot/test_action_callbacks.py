from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from bot.ui import action_view


@pytest.mark.asyncio
async def test_actual_approve_callback_uses_factory_and_signature(monkeypatch):
    client=AsyncMock()
    response=MagicMock(status_code=200)
    response.json.return_value={'execution':{'success':True,'content':'done'}}
    client.post.return_value=response
    @asynccontextmanager
    async def factory(**kwargs): yield client
    monkeypatch.setattr(action_view,'api_client',factory)
    interaction=SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()),user=SimpleNamespace(id=1),guild=None,edit_original_response=AsyncMock(),followup=SimpleNamespace(send=AsyncMock()))
    view=action_view.ActionConfirmationView('a','1','write',{},signature='a'*64)
    await view.approve_button.callback(interaction)
    assert client.post.call_args.kwargs['json']['signature']=='a'*64
    interaction.edit_original_response.assert_awaited_once()


@pytest.mark.asyncio
async def test_denial_error_does_not_claim_success(monkeypatch):
    client=AsyncMock()
    client.post.return_value=MagicMock(status_code=403)
    @asynccontextmanager
    async def factory(**kwargs): yield client
    monkeypatch.setattr(action_view,'api_client',factory)
    interaction=SimpleNamespace(response=SimpleNamespace(defer=AsyncMock()),user=SimpleNamespace(id=1),guild=None,edit_original_response=AsyncMock(),followup=SimpleNamespace(send=AsyncMock()))
    view=action_view.ActionConfirmationView('a','1','write',{})
    await view.deny_button.callback(interaction)
    interaction.edit_original_response.assert_not_awaited()
    interaction.followup.send.assert_awaited_once()
