import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest
from backend.sandbox import code_runner
from backend.config import settings
from backend.routers.sandbox import run_code, CodeExecRequest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_cancellation_kills_process_and_container_before_return(monkeypatch):
    entered=asyncio.Event()
    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()
    proc=MagicMock()
    proc.returncode=None
    proc.stdout.read=AsyncMock(side_effect=blocked)
    proc.stderr.read=AsyncMock(side_effect=blocked)
    async def wait():
        if proc.returncode is None: await asyncio.Event().wait()
    proc.wait=AsyncMock(side_effect=wait)
    proc.kill.side_effect=lambda: setattr(proc,'returncode',-9)
    monkeypatch.setattr(asyncio,'create_subprocess_exec',AsyncMock(return_value=proc))
    cleanup=AsyncMock()
    monkeypatch.setattr(code_runner,'_cleanup_container',cleanup)
    task=asyncio.create_task(code_runner.execute_code_docker('print(1)'))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError): await task
    proc.kill.assert_called_once()
    cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_shared_spool_uses_host_mapping_and_never_pulls(monkeypatch,tmp_path):
    monkeypatch.setattr(settings,'SANDBOX_SPOOL_DIR',str(tmp_path))
    monkeypatch.setattr(settings,'SANDBOX_HOST_SPOOL_DIR','/host/spool')
    proc=MagicMock(returncode=0)
    proc.stdout.read=AsyncMock(side_effect=[b'ok',b''])
    proc.stderr.read=AsyncMock(return_value=b'')
    proc.wait=AsyncMock(return_value=0)
    create=AsyncMock(return_value=proc)
    monkeypatch.setattr(asyncio,'create_subprocess_exec',create)
    result=await code_runner.execute_code_docker('print(1)')
    command=create.call_args.args
    assert '/host/spool/' in command[command.index('-v')+1]
    assert command[command.index('--pull')+1]=='never'
    assert command[command.index('--log-driver')+1]=='none'
    assert not list(tmp_path.iterdir())
    assert result['success']


@pytest.mark.asyncio
async def test_manual_missing_context_and_profile_fail_closed(monkeypatch):
    from backend.memory.db import db_helper
    monkeypatch.setattr(db_helper,'get_channel_profile',AsyncMock(return_value=None))
    for channel in (None,'unconfigured'):
        with pytest.raises(HTTPException) as exc:
            await run_code(CodeExecRequest(code='print(1)',channel_id=channel))
        assert exc.value.status_code==403


@pytest.mark.asyncio
async def test_one_failed_verification_allows_one_repair():
    from backend.agent.runtime import AgentRuntime
    from backend.agent.types import AgentModelTurn, ToolCall
    from backend.tools.base import ToolSpec, ToolResult
    router=AsyncMock()
    router.generate_agent_turn.side_effect=[AgentModelTurn(tool_calls=[ToolCall('a','code.execute',{'code':'bad'})]),AgentModelTurn(tool_calls=[ToolCall('b','code.execute',{'code':'good'})]),AgentModelTurn(text='done')]
    executor=AsyncMock()
    executor.execute.side_effect=[ToolResult('code.execute',False,content={'exit_code':1}),ToolResult('code.execute',True,content={'exit_code':0})]
    result=await AgentRuntime(router,executor).run([], 'gemini','gemini-2.5-flash','', tools=[ToolSpec('code.execute','',{},risk='privileged')],allow_code_exec=True,auto_code_test_mode='auto')
    assert executor.execute.await_count==2 and result.sandbox_calls==2
