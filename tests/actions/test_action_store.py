"""Tests for InMemoryActionStore and SupabaseActionStore implementations."""

import time
import pytest
from unittest.mock import MagicMock, patch
from backend.actions.models import PendingAction
from backend.actions.store import InMemoryActionStore, SupabaseActionStore


@pytest.mark.asyncio
async def test_in_memory_action_store_crud():
    store = InMemoryActionStore()
    now = time.time()

    action = PendingAction(
        action_id="act-1",
        channel_id="c1",
        user_id="u1",
        tool_name="github.create_issue",
        arguments={"title": "Fix bug"},
        risk="write",
        expires_at=now + 100,
    )

    # Create
    created = await store.create(action)
    assert created.action_id == "act-1"

    # Get
    fetched = await store.get("act-1")
    assert fetched is not None
    assert fetched.tool_name == "github.create_issue"
    assert fetched.status == "pending"

    # Update status to approved
    updated = await store.update_status("act-1", "approved")
    assert updated.status == "approved"

    # Update status to executed
    executed = await store.update_status("act-1", "executed")
    assert executed.status == "executed"
    assert executed.executed_at is not None

    # Missing ID returns None
    missing = await store.get("non-existent")
    assert missing is None


@pytest.mark.asyncio
async def test_in_memory_action_store_auto_expiration():
    store = InMemoryActionStore()
    now = time.time()

    # Expired action
    expired_action = PendingAction(
        action_id="act-exp",
        channel_id="c1",
        user_id="u1",
        tool_name="github.create_issue",
        arguments={},
        created_at=now - 200,
        expires_at=now - 50,
    )
    await store.create(expired_action)

    # get() auto-transitions status to 'expired'
    fetched = await store.get("act-exp")
    assert fetched is not None
    assert fetched.status == "expired"

    # cleanup_expired marks pending expired actions
    pending_exp = PendingAction(
        action_id="act-pending-exp",
        channel_id="c1",
        user_id="u1",
        tool_name="tool.write",
        arguments={},
        expires_at=now - 10,
    )
    await store.create(pending_exp)
    cleaned = await store.cleanup_expired()
    assert cleaned >= 1


@pytest.mark.asyncio
async def test_supabase_store_fallback_when_disconnected():
    # When Supabase is not connected, SupabaseActionStore transparently falls back to in-memory store
    with patch("backend.actions.store.is_supabase_connected", return_value=False):
        supabase_store = SupabaseActionStore()
        action = PendingAction(
            action_id="act-sb-fallback",
            channel_id="c1",
            user_id="u1",
            tool_name="github.create_issue",
            arguments={"repo": "zauq"},
            expires_at=time.time() + 100,
        )

        await supabase_store.create(action)
        fetched = await supabase_store.get("act-sb-fallback")
        assert fetched is not None
        assert fetched.arguments == {"repo": "zauq"}
