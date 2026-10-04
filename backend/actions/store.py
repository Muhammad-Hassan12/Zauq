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
        expected_status: Optional[ActionStatus] = None,
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
            if len(self._actions) >= 1000:
                terminal = next((key for key,value in self._actions.items() if value.status in ('denied','expired','executed') or value.is_expired()), None)
                if terminal is None:
                    raise RuntimeError('Pending action capacity reached')
                self._actions.pop(terminal)
            self._actions[action.action_id] = action.model_copy(deep=True)
            return action

    async def get(self, action_id: str) -> Optional[PendingAction]:
        async with self._lock:
            action = self._actions.get(action_id)
            if not action:
                return None

            # Auto-expire if time has passed and still pending
            if action.status in ('pending','approved') and action.is_expired():
                action.status = "expired"
                self._actions[action_id] = action

            return action.model_copy(deep=True)

    async def update_status(
        self,
        action_id: str,
        status: ActionStatus,
        executed_at: Optional[float] = None,
        expected_status: Optional[ActionStatus] = None,
    ) -> Optional[PendingAction]:
        async with self._lock:
            action = self._actions.get(action_id)
            if not action:
                return None
            expected = expected_status or {'approved':'pending','denied':'pending','executed':'approved'}.get(status)
            if expected is not None and action.status != expected:
                return None
            if action.status in ('denied','expired','executed'):
                return None
            if status in ('approved','executed') and action.is_expired():
                action.status='expired'
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
                if action.status in ('pending','approved') and action.expires_at <= now:
                    action.status = "expired"
                    count += 1
            for action_id, action in list(self._actions.items()):
                if action.status in ('denied','expired','executed') and action.expires_at < now - 3600:
                    del self._actions[action_id]
            return count


class SupabaseActionStore(ActionStore):
    """Durable actions fail closed. Only actions created offline use memory."""

    def __init__(self, fallback_store: Optional[ActionStore] = None) -> None:
        self._fallback = fallback_store or InMemoryActionStore()
        self._local_ids: dict[str, None] = {}

    def _client(self):
        client = get_supabase_client() if is_supabase_connected() else None
        if client is None:
            raise RuntimeError('Durable action storage is unavailable; execution is blocked')
        return client

    @staticmethod
    def _iso(timestamp):
        from datetime import datetime, timezone
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()

    @staticmethod
    def _action(row):
        from datetime import datetime
        values = dict(row)
        for key in ('created_at','expires_at','executed_at'):
            if values.get(key) is not None:
                values[key] = datetime.fromisoformat(values[key]).timestamp()
        return PendingAction.model_validate(values)

    async def create(self, action):
        if not is_supabase_connected():
            await self._fallback.cleanup_expired()
            self._local_ids[action.action_id] = None
            if len(self._local_ids) > 2000:
                self._local_ids.pop(next(iter(self._local_ids)))
            return await self._fallback.create(action)
        client = self._client()
        payload = action.model_dump()
        for key in ('created_at','expires_at'):
            payload[key] = self._iso(payload[key])
        if payload.get('executed_at') is not None:
            payload['executed_at'] = self._iso(payload['executed_at'])
        response = await asyncio.to_thread(lambda: client.table('pending_actions').insert(payload).execute())
        if not response.data:
            raise RuntimeError('Pending action was not persisted')
        return action

    async def get(self, action_id):
        if action_id in self._local_ids:
            return await self._fallback.get(action_id)
        client = self._client()
        response = await asyncio.to_thread(lambda: client.table('pending_actions').select('*').eq('action_id',action_id).limit(1).execute())
        if not response.data:
            return None
        action = self._action(response.data[0])
        if action.status in ('pending','approved') and action.is_expired():
            await self.update_status(action_id,'expired',expected_status=action.status)
            action.status='expired'
        return action

    async def update_status(self, action_id, status, executed_at=None, expected_status=None):
        expected = expected_status or {'approved':'pending','denied':'pending','executed':'approved'}.get(status)
        if not expected:
            raise ValueError('An expected state is required for durable transitions')
        if action_id in self._local_ids:
            return await self._fallback.update_status(action_id,status,executed_at,expected)
        client = self._client()
        update = {'status':status}
        if status=='executed':
            update['executed_at']=self._iso(executed_at or time.time())
        def claim():
            query=client.table('pending_actions').update(update).eq('action_id',action_id).eq('status',expected)
            if status in ('approved','executed','denied'):
                query=query.gt('expires_at',self._iso(time.time()))
            return query.execute()
        response=await asyncio.to_thread(claim)
        if len(response.data or []) != 1:
            return None
        return self._action(response.data[0])

    async def cleanup_expired(self):
        count=await self._fallback.cleanup_expired()
        if is_supabase_connected():
            client=self._client()
            response=await asyncio.to_thread(lambda: client.table('pending_actions').update({'status':'expired'}).in_('status',['pending','approved']).lte('expires_at',self._iso(time.time())).execute())
            count+=len(response.data or [])
            await asyncio.to_thread(lambda: client.table('pending_actions').delete().in_('status',['denied','expired','executed']).lt('expires_at',self._iso(time.time()-86400)).execute())
        return count


# Global default store instance
default_action_store = SupabaseActionStore()


def get_action_store() -> ActionStore:
    """Return the active global ActionStore."""
    return default_action_store
