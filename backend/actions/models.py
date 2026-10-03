"""Models and schemas for Phase 7: Side-Effect Approval / Human-in-the-Loop."""

from __future__ import annotations
import time
from typing import Any, Literal
from pydantic import BaseModel, Field
from backend.tools.base import RiskLevel

ActionStatus = Literal["pending", "approved", "denied", "expired", "executed"]


class PendingAction(BaseModel):
    """Represents a staged write/destructive tool action requiring human confirmation."""
    action_id: str
    guild_id: str | None = None
    channel_id: str
    user_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel = "write"
    status: ActionStatus = "pending"
    created_at: float = Field(default_factory=time.time)
    expires_at: float
    executed_at: float | None = None
    signature: str | None = None

    def is_expired(self) -> bool:
        """Check if action is past its expiration time."""
        return time.time() >= self.expires_at

    def can_be_acted_upon(self) -> bool:
        """True if action is pending and has not yet expired."""
        return self.status == "pending" and not self.is_expired()


class ActionCreateRequest(BaseModel):
    """Payload to create a staged pending action."""
    guild_id: str | None = None
    channel_id: str
    user_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    risk: RiskLevel = "write"
    ttl_seconds: int = 300


class ActionApproveRequest(BaseModel):
    """Payload to approve a pending action."""
    user_id: str
    signature: str | None = None
    is_admin: bool = False


class ActionDenyRequest(BaseModel):
    """Payload to deny a pending action."""
    user_id: str
    is_admin: bool = False


class ActionResponse(BaseModel):
    """Standard API response for action queries."""
    action: PendingAction
    can_approve: bool = False
