"""Tests for ActionService authorization, token validation, and single-use execution."""

import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.actions.service import (
    ActionService,
    generate_action_signature,
    verify_action_signature,
)
from backend.actions.store import InMemoryActionStore
from backend.tools.base import ToolSpec, ToolResult
from backend.tools.registry import ToolRegistry
from backend.tools.policy import ToolPolicy
from backend.tools.executor import ToolExecutor


def test_signature_generation_and_verification():
    sig = generate_action_signature("act-1", "user-1", "github.create_issue", 1700000000.0)
    assert isinstance(sig, str) and len(sig) == 64

    # Valid
    assert verify_action_signature(sig, "act-1", "user-1", "github.create_issue", 1700000000.0) is True

    # Tampered user_id
    assert verify_action_signature(sig, "act-1", "user-attacker", "github.create_issue", 1700000000.0) is False

    # Tampered tool_name
    assert verify_action_signature(sig, "act-1", "user-1", "database.drop_table", 1700000000.0) is False


@pytest.mark.asyncio
async def test_action_service_create_and_approve_by_initiator():
    store = InMemoryActionStore()
    service = ActionService(store=store)

    action = await service.create_action(
        channel_id="chan-1",
        user_id="user-123",
        tool_name="github.create_issue",
        arguments={"title": "Fix bug in API"},
        guild_id="guild-456",
        risk="write",
        ttl_seconds=300,
    )
    assert action.status == "pending"
    assert action.signature is not None

    # Initiating user approves
    approved = await service.approve_action(action.action_id, user_id="user-123")
    assert approved.status == "approved"


@pytest.mark.asyncio
async def test_action_service_approve_rejects_unauthorized_user():
    store = InMemoryActionStore()
    service = ActionService(store=store)

    action = await service.create_action(
        channel_id="chan-1",
        user_id="user-owner",
        tool_name="github.create_pr",
        arguments={},
        risk="write",
    )

    # Different user tries to approve -> PermissionError
    with pytest.raises(PermissionError, match="not authorized"):
        await service.approve_action(action.action_id, user_id="user-stranger", is_admin=False)

    # Server admin override succeeds
    admin_approved = await service.approve_action(action.action_id, user_id="user-admin", is_admin=True)
    assert admin_approved.status == "approved"


@pytest.mark.asyncio
async def test_action_service_deny():
    store = InMemoryActionStore()
    service = ActionService(store=store)

    action = await service.create_action(
        channel_id="chan-1",
        user_id="user-1",
        tool_name="github.delete_branch",
        arguments={"branch": "old-feature"},
        risk="destructive",
    )

    denied = await service.deny_action(action.action_id, user_id="user-1")
    assert denied.status == "denied"

    # Cannot approve after denial
    with pytest.raises(ValueError, match="already denied"):
        await service.approve_action(action.action_id, user_id="user-1")


@pytest.mark.asyncio
async def test_action_service_single_use_execution(monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, 'MCP_ENABLED', True)
    store = InMemoryActionStore()
    service = ActionService(store=store)

    # Setup ToolRegistry & Executor with a write tool
    registry = ToolRegistry()
    policy = ToolPolicy()
    executor = ToolExecutor(registry, policy)

    executed_args = []

    async def mock_handler(args):
        executed_args.append(args)
        return "Issue #42 created successfully"

    spec = ToolSpec(
        name="github.create_issue",
        description="Create issue",
        input_schema={},
        source="mcp",
        risk="write",
    )
    registry.register(spec, mock_handler)

    action = await service.create_action(
        channel_id="chan-1",
        user_id="user-1",
        tool_name="github.create_issue",
        arguments={"title": "Test Issue"},
        risk="write",
    )

    # Must be approved before execution
    res_unapproved = await service.execute_approved_action(action.action_id, executor)
    assert res_unapproved.success is False
    assert "pending" in res_unapproved.error

    # Approve
    await service.approve_action(action.action_id, user_id="user-1")

    # Execute approved action
    res_exec = await service.execute_approved_action(action.action_id, executor)
    assert res_exec.success is True
    assert res_exec.content == "Issue #42 created successfully"
    assert len(executed_args) == 1
    assert executed_args[0] == {"title": "Test Issue"}

    # Replay protection: executing a second time fails
    res_replay = await service.execute_approved_action(action.action_id, executor)
    assert res_replay.success is False
    assert "executed" in res_replay.error
    assert len(executed_args) == 1  # Not executed again
