import asyncio
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.actions.service import ActionService
from backend.actions.store import InMemoryActionStore, SupabaseActionStore
from backend.tools.base import ToolResult
from backend.tools.base import ToolSpec
from backend.tools.executor import ToolExecutor
from backend.tools.policy import ToolPolicy
from backend.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_concurrent_claims_dispatch_exactly_one_attempt():
    service=ActionService(InMemoryActionStore())
    action=await service.create_action(channel_id='c',user_id='u',tool_name='write',arguments={'title':'x'})
    await service.approve_action(action.action_id,'u',action.signature)
    executor=AsyncMock()
    executor.execute.return_value=ToolResult('write',True,'done')
    results=await asyncio.gather(*(service.execute_approved_action(action.action_id,executor) for _ in range(10)))
    assert sum(r.success for r in results)==1
    assert executor.execute.await_count==1


@pytest.mark.asyncio
async def test_changed_arguments_fail_signature_check():
    store=InMemoryActionStore()
    service=ActionService(store)
    action=await service.create_action(channel_id='c',user_id='u',tool_name='write',arguments={'title':'x'})
    store._actions[action.action_id].arguments['title']='tampered'
    with pytest.raises(ValueError,match='signature'):
        await service.approve_action(action.action_id,'u',action.signature)


@pytest.mark.asyncio
async def test_approved_action_cannot_execute_after_expiry(monkeypatch):
    store=InMemoryActionStore()
    service=ActionService(store)
    action=await service.create_action(channel_id='c',user_id='u',tool_name='write',arguments={})
    await service.approve_action(action.action_id,'u',action.signature)
    monkeypatch.setattr('backend.actions.store.time.time',lambda:action.expires_at+1)
    executor=AsyncMock()
    result=await service.execute_approved_action(action.action_id,executor)
    assert not result.success
    executor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_error_never_replays_fallback(monkeypatch):
    client=MagicMock()
    client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect=RuntimeError('outage')
    monkeypatch.setattr('backend.actions.store.is_supabase_connected',lambda:True)
    monkeypatch.setattr('backend.actions.store.get_supabase_client',lambda:client)
    fallback=AsyncMock()
    store=SupabaseActionStore(fallback)
    with pytest.raises(RuntimeError,match='outage'):
        await store.get('durable-id')
    fallback.get.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('revocation', ['risk', 'guild', 'master'])
async def test_approved_action_rechecks_current_policy(monkeypatch, revocation):
    from backend.config import settings
    from backend.memory.db import db_helper
    service = ActionService(InMemoryActionStore())
    action = await service.create_action(channel_id='c', guild_id='g', user_id='u', tool_name='mcp.docs.write', arguments={}, risk='write')
    await service.approve_action(action.action_id, 'u', action.signature)
    registry = ToolRegistry()
    handler = AsyncMock(return_value='done')
    registry.register(ToolSpec('mcp.docs.write', 'write', {}, risk='privileged' if revocation == 'risk' else 'write', source='mcp', allowed_guild_ids=[] if revocation == 'guild' else ['g']), handler)
    monkeypatch.setattr(settings, 'MCP_ENABLED', revocation != 'master')
    monkeypatch.setattr(settings, 'MCP_ALLOWED_GUILD_IDS', '')
    monkeypatch.setattr(settings, 'MCP_ALLOWED_CHANNEL_IDS', '')
    monkeypatch.setattr(db_helper, 'get_channel_profile', AsyncMock(return_value={}))
    monkeypatch.setattr(db_helper, 'get_guild_config', AsyncMock(return_value={}))
    result = await service.execute_approved_action(action.action_id, ToolExecutor(registry, ToolPolicy()))
    assert not result.success
    handler.assert_not_awaited()
