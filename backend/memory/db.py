import asyncio
import logging
from supabase import create_client, Client
from backend.config import settings
from typing import Dict, Any, Optional, List

logger = logging.getLogger("zauq.db")

class DatabaseHelper:
    def __init__(self):
        self.supabase: Optional[Client] = None
        if settings.SUPABASE_URL and settings.SUPABASE_KEY:
            try:
                self.supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
            except Exception as e:
                logger.warning(f"Failed to initialize Supabase client: {e}")

    # Guild Configs
    async def get_guild_config(self, guild_id: str) -> Optional[Dict[str, Any]]:
        if not self.supabase or not guild_id or guild_id == "dm":
            return None
        res = await asyncio.to_thread(
            lambda: self.supabase.table("guild_configs").select("*").eq("guild_id", guild_id).execute()
        )
        return res.data[0] if res.data else None

    async def upsert_guild_config(
        self,
        guild_id: str,
        guild_name: Optional[str] = None,
        default_mode: Optional[str] = None,
        default_tier: Optional[int] = None,
        default_provider: Optional[str] = None,
        default_model_name: Optional[str] = None,
        admin_role_id: Optional[str] = None,
        moderation_enabled: Optional[bool] = None,
        moderation_sensitivity: Optional[str] = None
    ) -> Dict[str, Any]:
        if not self.supabase or not guild_id or guild_id == "dm":
            return {"guild_id": guild_id}

        existing = await self.get_guild_config(guild_id) or {}
        payload = {
            "guild_id": guild_id,
            "guild_name": guild_name or existing.get("guild_name", f"Guild {guild_id}"),
            "default_mode": default_mode or existing.get("default_mode", "hangout"),
            "default_tier": default_tier if default_tier is not None else existing.get("default_tier", 1),
            "default_provider": default_provider or existing.get("default_provider", "gemini"),
            "default_model_name": default_model_name or existing.get("default_model_name", "gemini-2.5-flash"),
            "admin_role_id": admin_role_id if admin_role_id is not None else existing.get("admin_role_id"),
            "moderation_enabled": moderation_enabled if moderation_enabled is not None else existing.get("moderation_enabled", False),
            "moderation_sensitivity": moderation_sensitivity or existing.get("moderation_sensitivity", "medium")
        }
        res = await asyncio.to_thread(
            lambda: self.supabase.table("guild_configs").upsert(payload).execute()
        )
        return res.data[0] if res.data else payload

    # Channel Profiles
    async def get_channel_profile(self, channel_id: str) -> Optional[Dict[str, Any]]:
        if not self.supabase or not channel_id:
            return None
        res = await asyncio.to_thread(
            lambda: self.supabase.table("channel_profiles").select("*").eq("channel_id", channel_id).execute()
        )
        return res.data[0] if res.data else None

    async def upsert_channel_profile(
        self, channel_id: str, guild_id: str, operating_mode: str,
        system_persona_prompt: str = None, temperature: float = 0.7,
        allow_code_exec: bool = False, thinking_enabled: bool = False
    ) -> Dict[str, Any]:
        if not self.supabase:
            return {"channel_id": channel_id, "operating_mode": operating_mode}
        # Ensure parent guild_config exists first
        if guild_id and guild_id != "dm":
            try:
                await asyncio.to_thread(
                    lambda: self.supabase.table("guild_configs").upsert({"guild_id": guild_id, "guild_name": f"Guild {guild_id}"}).execute()
                )
            except Exception:
                pass
        payload = {
            "channel_id": channel_id,
            "guild_id": guild_id or "dm",
            "operating_mode": operating_mode,
            "system_persona_prompt": system_persona_prompt,
            "temperature": temperature,
            "allow_code_exec": allow_code_exec,
            "thinking_enabled": thinking_enabled
        }
        res = await asyncio.to_thread(
            lambda: self.supabase.table("channel_profiles").upsert(payload).execute()
        )
        return res.data[0] if res.data else payload

    async def set_channel_thinking(self, channel_id: str, guild_id: str, enabled: bool) -> Dict[str, Any]:
        """Set only the thinking_enabled flag on a channel profile, preserving all other settings."""
        if not self.supabase:
            return {"channel_id": channel_id, "thinking_enabled": enabled}
        # Ensure guild exists
        if guild_id and guild_id != "dm":
            try:
                await asyncio.to_thread(
                    lambda: self.supabase.table("guild_configs").upsert({"guild_id": guild_id, "guild_name": f"Guild {guild_id}"}).execute()
                )
            except Exception:
                pass
        # Fetch existing profile to preserve other fields
        existing = await self.get_channel_profile(channel_id) or {}
        payload = {
            "channel_id": channel_id,
            "guild_id": existing.get("guild_id", guild_id or "dm"),
            "operating_mode": existing.get("operating_mode", "hangout"),
            "system_persona_prompt": existing.get("system_persona_prompt"),
            "temperature": existing.get("temperature", 0.7),
            "allow_code_exec": existing.get("allow_code_exec", False),
            "thinking_enabled": enabled
        }
        res = await asyncio.to_thread(
            lambda: self.supabase.table("channel_profiles").upsert(payload).execute()
        )
        return res.data[0] if res.data else payload

    async def delete_channel_profile(self, channel_id: str) -> bool:
        """Deletes a channel-specific profile override so the channel inherits server defaults."""
        if not self.supabase or not channel_id:
            return False
        try:
            await asyncio.to_thread(
                lambda: self.supabase.table("channel_profiles").delete().eq("channel_id", channel_id).execute()
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to delete channel profile for {channel_id}: {e}")
            return False

    # Model Selection
    async def get_model_selection(self, channel_id: str) -> Optional[Dict[str, Any]]:
        if not self.supabase or not channel_id:
            return None
        res = await asyncio.to_thread(
            lambda: self.supabase.table("model_selection").select("*").eq("channel_id", channel_id).execute()
        )
        return res.data[0] if res.data else None

    async def upsert_model_selection(
        self, channel_id: str, tier: int, provider: str, model_name: str, updated_by: str = ""
    ) -> Dict[str, Any]:
        if not self.supabase:
            return {"channel_id": channel_id, "tier": tier, "provider": provider, "model_name": model_name}
        payload = {
            "channel_id": channel_id,
            "tier": tier,
            "provider": provider,
            "model_name": model_name,
            "updated_by": updated_by
        }
        res = await asyncio.to_thread(
            lambda: self.supabase.table("model_selection").upsert(payload).execute()
        )
        return res.data[0] if res.data else payload

    async def delete_model_selection(self, channel_id: str) -> bool:
        """Deletes a channel-specific model selection override so the channel inherits server defaults."""
        if not self.supabase or not channel_id:
            return False
        try:
            await asyncio.to_thread(
                lambda: self.supabase.table("model_selection").delete().eq("channel_id", channel_id).execute()
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to delete model selection for {channel_id}: {e}")
            return False

    # -------------------------------------------------------------------------
    # User Memories (L2 Semantic Vector Store)
    # -------------------------------------------------------------------------

    async def get_user_memories(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Recency-based fallback fetch (used when embeddings are unavailable)."""
        if not self.supabase:
            return []
        res = await asyncio.to_thread(
            lambda: self.supabase.table("user_memories").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        )
        return res.data or []

    async def search_user_memories_by_vector(
        self,
        user_id: str,
        query_embedding: List[float],
        threshold: float = 0.65,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Vector similarity search via the match_user_memories RPC.
        Results are ranked by similarity * importance_score (relevance + weight).
        Falls back to recency query if RPC is unavailable or returns empty.
        """
        if not self.supabase:
            return []
        try:
            rpc_res = await asyncio.to_thread(
                lambda: self.supabase.rpc(
                    "match_user_memories",
                    {
                        "query_embedding": query_embedding,
                        "match_user_id": user_id,
                        "match_threshold": threshold,
                        "match_count": limit
                    }
                ).execute()
            )
            if rpc_res.data:
                return rpc_res.data
        except Exception as rpc_err:
            logger.info(f"match_user_memories RPC fallback for user {user_id}: {rpc_err}")
        # Graceful fallback to recency query
        return await self.get_user_memories(user_id, limit=limit)

    async def reinforce_memory(self, memory_id: str) -> None:
        """
        Increment access_count and update last_accessed_at for a retrieved memory.
        This acts as a reinforcement signal — frequently accessed memories retain higher importance.
        """
        if not self.supabase or not memory_id:
            return
        try:
            # Read current access_count first, then increment
            res = await asyncio.to_thread(
                lambda: self.supabase.table("user_memories")
                    .select("access_count")
                    .eq("memory_id", memory_id)
                    .execute()
            )
            current_count = res.data[0].get("access_count", 0) if res.data else 0
            await asyncio.to_thread(
                lambda: self.supabase.table("user_memories")
                    .update({
                        "access_count": current_count + 1,
                        "last_accessed_at": "NOW()"
                    })
                    .eq("memory_id", memory_id)
                    .execute()
            )
        except Exception as e:
            logger.debug(f"Memory reinforcement skipped for {memory_id}: {e}")

    async def add_user_memory(
        self, user_id: str, fact_content: str, category: str = "general",
        embedding: Optional[List[float]] = None, confidence_score: float = 1.0,
        importance_score: float = 1.0
    ) -> Dict[str, Any]:
        if not self.supabase:
            return {}
        payload = {
            "user_id": user_id,
            "category": category,
            "fact_content": fact_content,
            "confidence_score": confidence_score,
            "importance_score": importance_score
        }
        if embedding:
            payload["embedding"] = embedding
        res = await asyncio.to_thread(
            lambda: self.supabase.table("user_memories").insert(payload).execute()
        )
        return res.data[0] if res.data else payload

    async def halve_memory_importance(self, memory_id: str) -> None:
        """Halve the importance_score of a contradicted memory."""
        if not self.supabase or not memory_id:
            return
        try:
            res = await asyncio.to_thread(
                lambda: self.supabase.table("user_memories")
                    .select("importance_score")
                    .eq("memory_id", memory_id)
                    .execute()
            )
            current = res.data[0].get("importance_score", 1.0) if res.data else 1.0
            await asyncio.to_thread(
                lambda: self.supabase.table("user_memories")
                    .update({"importance_score": round(current * 0.5, 4)})
                    .eq("memory_id", memory_id)
                    .execute()
            )
        except Exception as e:
            logger.debug(f"Could not halve memory importance for {memory_id}: {e}")

    async def decay_old_memories(self, days_threshold: int = 30, decay_rate: float = 0.05) -> int:
        """
        Reduce importance_score by decay_rate for memories not accessed in days_threshold days.
        Returns the number of memories decayed.
        """
        if not self.supabase:
            return 0
        try:
            # Fetch memories to decay
            cutoff_date = f"NOW() - INTERVAL '{days_threshold} days'"
            res = await asyncio.to_thread(
                lambda: self.supabase.table("user_memories")
                    .select("memory_id, importance_score")
                    .lt("last_accessed_at", cutoff_date)
                    .gt("importance_score", 0.1)
                    .execute()
            )
            memories = res.data or []
            for mem in memories:
                new_score = round(mem["importance_score"] * (1.0 - decay_rate), 4)
                await asyncio.to_thread(
                    lambda mid=mem["memory_id"], ns=new_score: self.supabase.table("user_memories")
                        .update({"importance_score": ns})
                        .eq("memory_id", mid)
                        .execute()
                )
            logger.info(f"Memory decay: reduced importance_score for {len(memories)} memories.")
            return len(memories)
        except Exception as e:
            logger.warning(f"Memory decay failed: {e}")
            return 0

    async def delete_expired_memories(self, min_importance: float = 0.15) -> int:
        """
        Delete memories whose importance_score has decayed below min_importance.
        Returns the number of memories pruned.
        """
        if not self.supabase:
            return 0
        try:
            res = await asyncio.to_thread(
                lambda: self.supabase.table("user_memories")
                    .delete()
                    .lt("importance_score", min_importance)
                    .execute()
            )
            count = len(res.data) if res.data else 0
            if count > 0:
                logger.info(f"Memory expiry: pruned {count} expired memories (importance < {min_importance}).")
            return count
        except Exception as e:
            logger.warning(f"Memory expiry failed: {e}")
            return 0

db_helper = DatabaseHelper()
