import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks, HTTPException

from backend.chat.orchestrator import ChatOrchestrator
from backend.config import settings
from backend.memory.usage import record_usage, usage_records
from backend.memory.metrics import estimate_provider_cost, log_request_metric


@pytest.mark.asyncio
async def test_deadline_covers_context_and_cancels(monkeypatch):
    monkeypatch.setattr(settings,'AGENT_TOTAL_TIMEOUT_SECONDS',.02)
    cancelled = asyncio.Event()
    async def build(req):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()
    orchestrator = ChatOrchestrator(context_builder_inst=MagicMock(build=build))
    req = MagicMock(deep_search=False,file_generation=False)
    with pytest.raises(HTTPException) as error:
        await orchestrator.run(req,BackgroundTasks())
    assert error.value.status_code == 504
    assert cancelled.is_set()
    assert usage_records.get() is None


def test_unknown_pricing_and_physical_mixed_usage(monkeypatch):
    monkeypatch.setattr(settings,'MODEL_PRICING_JSON','{}')
    assert estimate_provider_cost('gemini','anything',10,20) is None
    records = []
    token = usage_records.set(records)
    try:
        record_usage('gemini','a',{'usageMetadata':{'promptTokenCount':10,'candidatesTokenCount':20,'thoughtsTokenCount':5}})
        record_usage('anthropic','b',{'usage':{'input_tokens':3,'output_tokens':4}})
        assert records[0]['output_tokens'] == 25
        assert records[1]['provider'] == 'anthropic'
    finally:
        usage_records.reset(token)


@pytest.mark.asyncio
async def test_durable_metrics_include_v4_fields(monkeypatch):
    from backend.memory.metrics import db_helper
    client = MagicMock()
    monkeypatch.setattr(db_helper,'supabase',client)
    await log_request_metric(None,'c',None,2,'ollama','m',10,tool_steps=3,request_id='r',provider_usage=[{'provider':'ollama','model':'m','input_tokens':None,'output_tokens':None}])
    payload = client.table.return_value.insert.call_args.args[0]
    assert payload['tool_steps'] == 3
    assert payload['request_id'] == 'r'
    assert payload['provider_usage'][0]['provider'] == 'ollama'
    assert payload['estimated_cost_usd'] is None


@pytest.mark.asyncio
async def test_local_metrics_preserve_unknown_usage_and_cost(monkeypatch):
    from backend.memory import metrics
    monkeypatch.setattr(metrics, 'IN_MEMORY_LOGS', [])
    await metrics.log_request_metric('g', 'c', 'u', 1, 'gemini', 'm', 10, input_tokens=None, output_tokens=None)
    summary = await metrics.get_metrics_summary('g')
    assert summary['unknown_usage_requests'] == 1
    assert summary['unknown_cost_requests'] == 1
    assert summary['total_estimated_cost_usd'] is None
