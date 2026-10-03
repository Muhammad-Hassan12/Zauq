"""Storage backends for Pending Actions in Zauq v4.

Provides both in-memory store (for fast isolated tests and offline mode)
and Supabase-backed store (for production durability across bot restarts).
"""

from __future__ import annotations
import asyncio
import time
import logging
from abc import ABC, abstractmethod
from typing import Optional

from backend.actions.models import PendingAction, ActionStatus
from backend.memory.db import is_supabase_connected, get_supabase_client

logger = logging.getLogger("zauq.actions.store")


class ActionStore(ABC):
    """Abstract interface for storing and retrieving PendingAction records."""

    @abstractmethod
    async def create(self, action: PendingAction) -> PendingAction:
        """Persist a new pending action."""
        pass

    @abstractmethod
    async def get(self, action_id: str) -> Optional[PendingAction]:
        """Fetch an action by ID. Auto-updates status to expired if TTL has passed."""
        pass

    @abstractmethod
    async def update_status(
        self,
        action_id: str,
        status: ActionStatus,
        executed_at: Optional[float] = None,
    ) -> Optional[PendingAction]:
        """Atomically transition action status."""
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Mark or remove all expired pending actions."""
        pass


class InMemoryActionStore(ActionStore):
    """In-memory, thread-safe storage for pending actions."""

    def __init__(self) -> None:
        self._actions: dict[str, PendingAction] = {}
        self._lock = asyncio.Lock()

    async def create(self, action: PendingAction) -> PendingAction:
        async with self._lock:
            # Immutability guarantee: store a model copy
            self._actions[action.action_id] = action.model_copy(deep=True)
            return action

    async def get(self, action_id: str) -> Optional[PendingAction]:
        async with self._lock:
            action = self._actions.get(action_id)
            if not action:
                return None

            # Auto-expire if time has passed and still pending
            if action.status == "pending" and action.is_expired():
                action.status = "expired"
                self._actions[action_id] = action

            return action.model_copy(deep=True)

    async def update_status(
        self,
        action_id: str,
        status: ActionStatus,
        executed_at: Optional[float] = None,
    ) -> Optional[PendingAction]:
        async with self._lock:
            action = self._actions.get(action_id)
            if not action:
                return None

            action.status = status
            if executed_at is not None:
                action.executed_at = executed_at
            elif status == "executed":
                action.executed_at = time.time()

            self._actions[action_id] = action
            return action.model_copy(deep=True)

    async def cleanup_expired(self) -> int:
        async with self._lock:
            now = time.time()
            count = 0
            for action in self._actions.values():
                if action.status == "pending" and action.expires_at <= now:
                    action.status = "expired"
                    count += 1
            return count


class SupabaseActionStore(ActionStore):
    """Durable Supabase storage for PendingAction with fallback to memory on error."""

    def __init__(self, fallback_store: Optional[ActionStore] = None) -> None:
        self._fallback = fallback_store or InMemoryActionStore()

    async def create(self, action: PendingAction) -> PendingAction:
        client = get_supabase_client()
        if not client or not is_supabase_connected():
            return await self._fallback.create(action)

        try:
            from datetime import datetime, timezone
            created_iso = datetime.fromtimestamp(action.created_at, tz=timezone.utc).isoformat()
            expires_iso = datetime.fromtimestamp(action.expires_at, tz=timezone.utc).isoformat()

            payload = {
                "action_id": action.action_id,
                "guild_id": action.guild_id,
                "channel_id": action.channel_id,
                "user_id": action.user_id,
                "tool_name": action.tool_name,
                "arguments": action.arguments,
                "risk": action.risk,
                "status": action.status,
                "created_at": created_iso,
                "expires_at": expires_iso,
            }
            client.table("pending_actions").insert(payload).execute()
            # Also keep fallback in sync
            await self._fallback.create(action)
            return action
        except Exception as e:
            logger.warning(f"Failed to persist pending_action to Supabase ({e}), using fallback store.")
            return await self._fallback.create(action)

    async def get(self, action_id: str) -> Optional[PendingAction]:
        client = get_supabase_client()
        if not client or not is_supabase_connected():
            return await self._fallback.get(action_id)

        try:
            from datetime import datetime, timezone
            res = client.table("pending_actions").select("*").eq("action_id", action_id).limit(1).execute()
            if not res.data:
                return await self._fallback.get(action_id)

            row = res.data[0]
            created_at = datetime.fromisoformat(row["created_at"]).timestamp()
            expires_at = datetime.fromisoformat(row["expires_at"]).timestamp()
            executed_at = datetime.fromisoformat(row["executed_at"]).timestamp() if row.get("executed_at") else None

            action = PendingAction(
                action_id=row["action_id"],
                guild_id=row.get("guild_id"),
                channel_id=row["channel_id"],
                user_id=row["user_id"],
                tool_name=row["tool_name"],
                arguments=row.get("arguments") or {},
                risk=row.get("risk", "write"),
                status=row.get("status", "pending"),
                created_at=created_at,
                expires_at=expires_at,
                executed_at=executed_at,
            )

            # Auto-expire check
            if action.status == "pending" and action.is_expired():
                await self.update_status(action_id, "expired")
                action.status = "expired"

            return action
        except Exception as e:
            logger.warning(f"Failed to query pending_action from Supabase ({e}), checking fallback store.")
            return await self._fallback.get(action_id)

    async def update_status(
        self,
        action_id: str,
        status: ActionStatus,
        executed_at: Optional[float] = None,
    ) -> Optional[PendingAction]:
        client = get_supabase_client()
        if not client or not is_supabase_connected():
            return await self._fallback.update_status(action_id, status, executed_at)

        try:
            from datetime import datetime, timezone
            update_data: dict = {"status": status}
            now_ts = executed_at or time.time()
            if status == "executed":
                update_data["executed_at"] = datetime.fromtimestamp(now_ts, tz=timezone.utc).isoformat()

            client.table("pending_actions").update(update_data).eq("action_id", action_id).execute()
            return await self._fallback.update_status(action_id, status, executed_at)
        except Exception as e:
            logger.warning(f"Failed to update pending_action in Supabase ({e}), updating fallback store.")
            return await self._fallback.update_status(action_id, status, executed_at)

    async def cleanup_expired(self) -> int:
        return await self._fallback.cleanup_expired()


# Global default store instance
default_action_store = SupabaseActionStore()


def get_action_store() -> ActionStore:
    """Return the active global ActionStore."""
    return default_action_store
