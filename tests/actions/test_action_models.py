"""Tests for PendingAction data models and immutability invariants."""

import time
import pytest
from backend.actions.models import PendingAction, ActionCreateRequest, ActionApproveRequest, ActionDenyRequest


def test_pending_action_model_and_expiration():
    now = time.time()
    action = PendingAction(
        action_id="act-123",
        guild_id="guild-abc",
        channel_id="chan-xyz",
        user_id="user-456",
        tool_name="github.create_issue",
        arguments={"title": "Bug in API", "body": "Details"},
        risk="write",
        status="pending",
        created_at=now,
        expires_at=now + 300,
    )

    assert action.action_id == "act-123"
    assert action.is_expired() is False
    assert action.can_be_acted_upon() is True

    # Check expired action
    past_action = PendingAction(
        action_id="act-expired",
        channel_id="chan-xyz",
        user_id="user-456",
        tool_name="github.create_issue",
        arguments={},
        created_at=now - 400,
        expires_at=now - 10,
    )
    assert past_action.is_expired() is True
    assert past_action.can_be_acted_upon() is False


def test_pending_action_immutability():
    initial_args = {"repo": "owner/zauq", "action": "deploy"}
    action = PendingAction(
        action_id="act-immut",
        channel_id="c1",
        user_id="u1",
        tool_name="deploy.trigger",
        arguments=initial_args,
        expires_at=time.time() + 60,
    )

    # Modifying the original dict does not mutate action arguments
    initial_args["repo"] = "malicious/override"
    assert action.arguments["repo"] == "owner/zauq"


def test_action_request_schemas():
    create_req = ActionCreateRequest(
        channel_id="c1",
        user_id="u1",
        tool_name="github.create_pr",
        arguments={"branch": "feature"},
        risk="write",
        ttl_seconds=120,
    )
    assert create_req.ttl_seconds == 120
    assert create_req.arguments == {"branch": "feature"}

    approve_req = ActionApproveRequest(user_id="u1", is_admin=True, signature='a'*64)
    assert approve_req.is_admin is True

    deny_req = ActionDenyRequest(user_id="u1")
    assert deny_req.user_id == "u1"
