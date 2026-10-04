import pytest
from unittest.mock import AsyncMock
from backend.tools.base import ToolSpec
from backend.tools.registry import ToolRegistry
from backend.tools.executor import ToolExecutor
from backend.tools.policy import ToolPolicy
from backend.config import settings


@pytest.mark.asyncio
async def test_schema_and_request_scope_block_before_handler():
    reg = ToolRegistry()
    handler = AsyncMock(return_value='ok')
    reg.register(ToolSpec('code.execute', '', {'type':'object', 'required':['code'], 'properties':{'code':{'type':'string'}, 'timeout':{'type':'integer','maximum':30}}}, risk='privileged'), handler)
    executor = ToolExecutor(reg, ToolPolicy({'code.execute'}))
    for args in ({'timeout':999}, {'code':'x','timeout':999}):
        assert not (await executor.execute('code.execute', args, allow_code_exec=True)).success
    assert not (await executor.execute('code.execute', {'code':'x'}, allow_code_exec=True, allowed_tools={'web.search'})).success
    assert not (await executor.execute('code.execute', {'code':'x'}, allow_code_exec=True, automatic=True, auto_code_test_mode='off')).success
    handler.assert_not_awaited()


def test_registration_rejects_remote_refs_and_invalid_schema():
    reg = ToolRegistry()
    for schema in ({'$ref':'https://example.com/schema'}, {'type':'nonsense'}):
        with pytest.raises(Exception):
            reg.register(ToolSpec('test', '', schema), AsyncMock())
        assert len(reg) == 0


def test_unusual_alias_round_trip_through_registry():
    reg = ToolRegistry()
    for name in ('mcp.server.name__with__underscores', 'mcp.server.'+'a'*100, 'mcp.server.tool with space'):
        reg.register(ToolSpec(name,'',{}), AsyncMock())
        alias = reg.aliases.get_alias(name)
        assert len(alias) <= 64
        assert reg.aliases.resolve(alias) == name


@pytest.mark.asyncio
async def test_output_and_exception_secrets_are_bounded(monkeypatch):
    monkeypatch.setattr(settings, 'INTERNAL_API_KEY', 'audit-secret-123')
    monkeypatch.setattr(settings, 'SANDBOX_MAX_OUTPUT_CHARS', 100)
    reg = ToolRegistry()
    reg.register(ToolSpec('read','',{}), AsyncMock(return_value='audit-secret-123'+'x'*500))
    result = await ToolExecutor(reg,ToolPolicy()).execute('read',{})
    assert 'audit-secret-123' not in result.content
    assert result.metadata['truncated']
