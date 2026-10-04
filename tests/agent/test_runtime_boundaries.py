from unittest.mock import AsyncMock
import pytest
from backend.agent.runtime import AgentRuntime
from backend.agent.types import AgentModelTurn, ToolCall
from backend.tools.base import ToolSpec
from backend.tools.registry import ToolRegistry
from backend.tools.executor import ToolExecutor
from backend.tools.policy import ToolPolicy
from backend.config import settings


def rig(turns):
    reg=ToolRegistry()
    handler=AsyncMock(return_value='ok')
    reg.register(ToolSpec('web.search','',{}), handler)
    reg.register(ToolSpec('code.execute','',{},risk='privileged'), handler)
    router=AsyncMock()
    router.generate_agent_turn.side_effect=turns
    router.generate.return_value='finished'
    return AgentRuntime(router,ToolExecutor(reg,ToolPolicy({'code.execute'}))), router,reg,handler


@pytest.mark.asyncio
async def test_unselected_code_cannot_run_with_automatic_off():
    runtime,router,reg,handler=rig([AgentModelTurn(tool_calls=[ToolCall('c','code.execute',{})]),AgentModelTurn(text='done')])
    result=await runtime.run([], 'gemini','gemini-2.5-flash','',tools=[reg.get('web.search')],allow_code_exec=True,auto_code_test_mode='off')
    handler.assert_not_awaited()
    assert not result.tool_trace[0]['success']


@pytest.mark.asyncio
async def test_configured_step_budget_and_continuation(monkeypatch):
    monkeypatch.setattr(settings,'AGENT_MAX_TOOL_STEPS',1)
    native={'provider':'gemini','content':{'role':'model','parts':[{'thoughtSignature':'sig'}]}}
    runtime,router,reg,handler=rig([AgentModelTurn(tool_calls=[ToolCall('c','web.search',{})],provider_continuation=native)])
    result=await runtime.run([], 'gemini','gemini-2.5-flash','',tools=[reg.get('web.search')])
    assert result.tool_steps==1 and handler.await_count==1
    assert router.generate.call_args.kwargs['messages'][0]['_provider_continuation']==native


@pytest.mark.asyncio
async def test_search_resource_budget_blocks_third_dispatch():
    turns=[AgentModelTurn(tool_calls=[ToolCall(str(i),'web.search',{'query':str(i)})]) for i in range(4)]
    runtime,router,reg,handler=rig(turns)
    result=await runtime.run([], 'gemini','gemini-2.5-flash','',tools=[reg.get('web.search')])
    assert handler.await_count==2
    assert result.search_calls==2


@pytest.mark.asyncio
async def test_provider_failure_after_dispatch_returns_partial_without_replay():
    runtime,router,reg,handler=rig([AgentModelTurn(tool_calls=[ToolCall('c','web.search',{})]),RuntimeError('provider failed')])
    result=await runtime.run([], 'gemini','gemini-2.5-flash','',tools=[reg.get('web.search')])
    assert result.incomplete and result.tool_steps==1
    assert handler.await_count==1
    assert 'without replaying' in result.final_response


@pytest.mark.asyncio
async def test_staged_confirmation_does_not_count_as_mcp_execution(monkeypatch):
    from backend.actions.service import action_service
    runtime, router, registry, handler = rig([
        AgentModelTurn(tool_calls=[ToolCall('w', 'mcp.docs.write', {})]),
        AgentModelTurn(text='Approve the staged action'),
    ])
    registry.register(ToolSpec('mcp.docs.write', 'write', {}, source='mcp', risk='write', allowed_guild_ids=['g']), handler)
    stage = AsyncMock(return_value=type('Action', (), {'action_id': 'staged'})())
    monkeypatch.setattr(action_service, 'create_action', stage)
    result = await runtime.run([], 'gemini', 'gemini-2.5-flash', '', tools=[registry.get('mcp.docs.write')], guild_id='g')
    assert result.mcp_calls == 0 and result.tool_failures == 0
    stage.assert_awaited_once()
    handler.assert_not_awaited()
