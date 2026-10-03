"""ActionService for managing Human-in-the-Loop side-effect approval workflows."""

from __future__ import annotations
import hmac
import hashlib
import time
import uuid
import logging
from typing import Any, Optional

from backend.config import settings
from backend.actions.models import PendingAction, ActionStatus
from backend.actions.store import ActionStore, get_action_store
from backend.tools.base import RiskLevel, ToolResult
from backend.tools.executor import ToolExecutor

logger = logging.getLogger("zauq.actions.service")


def _get_signing_key() -> bytes:
    """Return HMAC key from INTERNAL_API_KEY or fallback secret."""
    raw = getattr(settings, "INTERNAL_API_KEY", "") or "zauq_v4_action_signing_secret_key"
    return raw.encode("utf-8")


def generate_action_signature(action_id: str, user_id: str, tool_name: str, expires_at: float) -> str:
    """Generate deterministic HMAC-SHA256 signature for a pending action."""
    msg = f"{action_id}:{user_id}:{tool_name}:{int(expires_at)}".encode("utf-8")
    return hmac.new(_get_signing_key(), msg, hashlib.sha256).hexdigest()


def verify_action_signature(signature: str, action_id: str, user_id: str, tool_name: str, expires_at: float) -> bool:
    """Verify validity of an action signature."""
    expected = generate_action_signature(action_id, user_id, tool_name, expires_at)
    return hmac.compare_digest(signature, expected)


class ActionService:
    """Coordinates lifecycle, authorization, and single-use execution of pending actions."""

    def __init__(self, store: Optional[ActionStore] = None) -> None:
        self.store = store or get_action_store()

    async def create_action(
        self,
        *,
        channel_id: str,
        user_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        guild_id: Optional[str] = None,
        risk: RiskLevel = "write",
        ttl_seconds: int = 300,
    ) -> PendingAction:
        """Create a new staged pending action with cryptographic signature and expiration."""
        action_id = str(uuid.uuid4())
        now = time.time()
        expires_at = now + ttl_seconds

        signature = generate_action_signature(action_id, user_id, tool_name, expires_at)

        # Immutability: ensure dict copy
        safe_arguments = dict(arguments or {})

        action = PendingAction(
            action_id=action_id,
            guild_id=guild_id,
            channel_id=channel_id,
            user_id=user_id,
            tool_name=tool_name,
            arguments=safe_arguments,
            risk=risk,
            status="pending",
            created_at=now,
            expires_at=expires_at,
            signature=signature,
        )

        await self.store.create(action)
        logger.info(
            f"Created PendingAction(id={action_id}, tool='{tool_name}', risk={risk}, "
            f"user={user_id}, expires_in={ttl_seconds}s)"
        )
        return action

    async def get_action(self, action_id: str) -> Optional[PendingAction]:
        """Fetch action by ID with automatic expiration check."""
        return await self.store.get(action_id)

    async def approve_action(
        self,
        action_id: str,
        user_id: str,
        signature: Optional[str] = None,
        is_admin: bool = False,
    ) -> PendingAction:
        """Approve a pending action. Enforces authorization, non-expiration, and signature validity."""
        action = await self.store.get(action_id)
        if not action:
            raise KeyError(f"Pending action '{action_id}' not found.")

        if action.status == "expired" or action.is_expired():
            await self.store.update_status(action_id, "expired")
            logger.warning(f"Attempted to approve expired action '{action_id}' by user '{user_id}'.")
            raise ValueError(f"Action '{action_id}' has expired and cannot be approved.")

        if action.status != "pending":
            logger.warning(
                f"Attempted replay/re-approval of action '{action_id}' currently in status '{action.status}'."
            )
            raise ValueError(f"Action '{action_id}' is already {action.status} and cannot be approved.")

        # Authorization: only initiating user or explicit admin override
        if not is_admin and str(action.user_id) != str(user_id):
            logger.warning(
                f"Unauthorized approval attempt for action '{action_id}': "
                f"initiator={action.user_id}, attempted_by={user_id}"
            )
            raise PermissionError(
                f"User '{user_id}' is not authorized to approve action initiated by '{action.user_id}'."
            )

        # Signature verification if signature provided
        if signature:
            if not verify_action_signature(signature, action.action_id, action.user_id, action.tool_name, action.expires_at):
                logger.warning(f"Signature mismatch on action '{action_id}'.")
                raise ValueError("Invalid action signature token.")

        updated = await self.store.update_status(action_id, "approved")
        logger.info(
            f"Action '{action_id}' ({action.tool_name}) APPROVED by user '{user_id}' (admin={is_admin})."
        )
        return updated or action

    async def deny_action(
        self,
        action_id: str,
        user_id: str,
        is_admin: bool = False,
    ) -> PendingAction:
        """Deny a pending action."""
        action = await self.store.get(action_id)
        if not action:
            raise KeyError(f"Pending action '{action_id}' not found.")

        if action.status != "pending":
            raise ValueError(f"Action '{action_id}' is already {action.status} and cannot be denied.")

        if not is_admin and str(action.user_id) != str(user_id):
            raise PermissionError(
                f"User '{user_id}' is not authorized to deny action initiated by '{action.user_id}'."
            )

        updated = await self.store.update_status(action_id, "denied")
        logger.info(f"Action '{action_id}' ({action.tool_name}) DENIED by user '{user_id}'.")
        return updated or action

    async def execute_approved_action(
        self,
        action_id: str,
        executor: ToolExecutor,
    ) -> ToolResult:
        """Execute an approved action exactly once. Transitions status to 'executed'."""
        action = await self.store.get(action_id)
        if not action:
            return ToolResult(
                tool_name="unknown",
                success=False,
                error=f"Action '{action_id}' not found.",
            )

        # Single-use guarantee: only 'approved' actions can execute
        if action.status != "approved":
            logger.warning(
                f"Replay protection: refusal to execute action '{action_id}' in state '{action.status}'."
            )
            return ToolResult(
                tool_name=action.tool_name,
                success=False,
                error=f"Action '{action_id}' cannot be executed because status is '{action.status}'.",
            )

        # Mark as executed atomically before handler runs to prevent concurrent double-execution
        await self.store.update_status(action_id, "executed")

        logger.info(
            f"Executing approved tool '{action.tool_name}' for action '{action_id}'..."
        )

        try:
            # Execute through ToolExecutor with explicit is_approved=True flag
            res = await executor.execute(
                tool_name=action.tool_name,
                arguments=action.arguments,
                guild_id=action.guild_id,
                is_approved=True,
            )
            logger.info(
                f"Executed action '{action_id}' ({action.tool_name}): success={res.success}"
            )
            return res
        except Exception as e:
            logger.error(f"Error executing approved action '{action_id}': {e}")
            return ToolResult(
                tool_name=action.tool_name,
                success=False,
                error=f"Execution error: {e}",
            )


# Global singleton instance
action_service = ActionService()
