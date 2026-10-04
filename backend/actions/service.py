from __future__ import annotations
import hmac
import hashlib
import time
import uuid
import logging
import secrets
import json
import copy
from typing import Any, Optional

from backend.config import settings
from backend.actions.models import PendingAction, ActionStatus
from backend.actions.store import ActionStore, get_action_store
from backend.tools.base import RiskLevel, ToolResult
from backend.tools.executor import ToolExecutor

logger = logging.getLogger("zauq.actions.service")
_DEVELOPMENT_SIGNING_KEY = secrets.token_bytes(32)


def _get_signing_key() -> bytes:
    """Return HMAC key from INTERNAL_API_KEY or fallback secret."""
    raw = settings.INTERNAL_API_KEY
    return raw.encode('utf-8') if raw else _DEVELOPMENT_SIGNING_KEY


def generate_action_signature(action_id: str, user_id: str, tool_name: str, expires_at: float, arguments=None, guild_id=None, channel_id=None, risk=None) -> str:
    """Generate deterministic HMAC-SHA256 signature for a pending action."""
    msg = json.dumps([action_id,user_id,tool_name,round(expires_at,6),arguments or {},guild_id,channel_id,risk],sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    return hmac.new(_get_signing_key(), msg, hashlib.sha256).hexdigest()


def verify_action_signature(signature: str, action_id: str, user_id: str, tool_name: str, expires_at: float, **kwargs) -> bool:
    """Verify validity of an action signature."""
    expected = generate_action_signature(action_id, user_id, tool_name, expires_at, **kwargs)
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
        now = round(time.time(),6)
        expires_at = round(now + min(ttl_seconds,300),6)
        from backend.security.sanitizer import sanitize_object
        if sanitize_object(arguments) != arguments:
            raise ValueError('Credentials cannot be stored in pending-action arguments')

        signature = generate_action_signature(action_id, user_id, tool_name, expires_at, arguments, guild_id, channel_id, risk)

        # Immutability: ensure dict copy
        safe_arguments = copy.deepcopy(arguments or {})

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
        signature = signature or action.signature
        if signature:
            if not verify_action_signature(signature, action.action_id, action.user_id, action.tool_name, action.expires_at, arguments=action.arguments,guild_id=action.guild_id,channel_id=action.channel_id,risk=action.risk):
                logger.warning(f"Signature mismatch on action '{action_id}'.")
                raise ValueError("Invalid action signature token.")
        else:
            raise ValueError('Action has no valid signature; stage a new action')

        updated = await self.store.update_status(action_id, "approved", expected_status='pending')
        if updated is None:
            raise ValueError('Action changed or expired before approval')
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

        updated = await self.store.update_status(action_id, "denied", expected_status='pending')
        if updated is None:
            raise ValueError('Action changed or expired before denial')
        logger.info(f"Action '{action_id}' ({action.tool_name}) DENIED by user '{user_id}'.")
        return updated or action

    async def execute_approved_action(
        self,
        action_id: str,
        executor: ToolExecutor,
    ) -> ToolResult:
        """Claim a single approved execution attempt. Transitions status to 'executed'."""
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
        if not action.signature or not verify_action_signature(action.signature,action.action_id,action.user_id,action.tool_name,action.expires_at,arguments=action.arguments,guild_id=action.guild_id,channel_id=action.channel_id,risk=action.risk):
            return ToolResult(action.tool_name,False,error='Stored action integrity check failed')
        spec = executor.registry.get(action.tool_name) if isinstance(executor, ToolExecutor) else None
        if spec and spec.risk != action.risk:
            return ToolResult(action.tool_name,False,error='Tool risk changed; stage a new action')
        if spec and spec.source == 'mcp':
            from backend.agent.rollout import feature_enabled
            from backend.memory.db import db_helper
            profile = await db_helper.get_channel_profile(action.channel_id)
            guild = await db_helper.get_guild_config(action.guild_id) if action.guild_id else None
            if not feature_enabled('mcp',action.channel_id,action.guild_id,profile,guild):
                return ToolResult(action.tool_name,False,error='MCP is disabled for this action scope')
        claimed = await self.store.update_status(action_id, "executed", expected_status='approved')
        if claimed is None:
            return ToolResult(action.tool_name,False,error='Action expired or another caller already claimed execution')
        action = claimed

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
                error="Approved execution failed; this attempt will not be replayed.",
            )


# Global singleton instance
action_service = ActionService()
