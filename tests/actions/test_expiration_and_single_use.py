"""Tests for Action expiration, single-use guarantees, and replay protection."""

import time
import pytest
from backend.actions.service import ActionService
from backend.actions.store import InMemoryActionStore
from backend.tools.base import ToolSpec
from backend.tools.registry import ToolRegistry
from backend.tools.policy import ToolPolicy
from backend.tools.executor import ToolExecutor


@pytest.mark.asyncio
async def test_expired_action_cannot_be_approved():
    store = InMemoryActionStore()
    service = ActionService(store=store)

    # Action that expires immediately (ttl=0.01)
    action = await service.create_action(
        channel_id="c1",
        user_id="u1",
        tool_name="github.delete_branch",
        arguments={"branch": "staging"},
        risk="destructive",
        ttl_seconds=0.01,
    )

    # Wait for expiration
    import asyncio
    await asyncio.sleep(0.05)

    with pytest.raises(ValueError, match="expired"):
        await service.approve_action(action.action_id, user_id="u1")


@pytest.mark.asyncio
async def test_expired_action_cannot_be_executed():
    store = InMemoryActionStore()
    service = ActionService(store=store)

    registry = ToolRegistry()
    executor = ToolExecutor(registry, ToolPolicy())

    # Create and immediately mark as expired
    action = await service.create_action(
        channel_id="c1",
        user_id="u1",
        tool_name="github.create_pr",
        arguments={},
        ttl_seconds=10,
    )
    await store.update_status(action.action_id, "expired")

    res = await service.execute_approved_action(action.action_id, executor)
    assert res.success is False
    assert "expired" in res.error.lower()


@pytest.mark.asyncio
async def test_single_use_token_and_replay_protection():
    store = InMemoryActionStore()
    service = ActionService(store=store)

    registry = ToolRegistry()
    policy = ToolPolicy()
    executor = ToolExecutor(registry, policy)

    counter = {"calls": 0}

    async def mock_handler(args):
        counter["calls"] += 1
        return "Done"

    spec = ToolSpec(name="server.restart", description="Restart", input_schema={}, risk="destructive")
    registry.register(spec, mock_handler)

    action = await service.create_action(
        channel_id="c1",
        user_id="u1",
        tool_name="server.restart",
        arguments={},
        risk="destructive",
    )

    # Approve
    await service.approve_action(action.action_id, user_id="u1")

    # Execution 1: Success
    res1 = await service.execute_approved_action(action.action_id, executor)
    assert res1.success is True
    assert counter["calls"] == 1

    # Execution 2: Replay fails
    res2 = await service.execute_approved_action(action.action_id, executor)
    assert res2.success is False
    assert "executed" in res2.error
    assert counter["calls"] == 1  # Did not execute again!
