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
        system_persona_prompt: str = None, temperature: float = 0.7, allow_code_exec: bool = False
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
            "allow_code_exec": allow_code_exec
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

    # User Memories (Episodic)
    async def get_user_memories(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        if not self.supabase:
            return []
        res = await asyncio.to_thread(
            lambda: self.supabase.table("user_memories").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        )
        return res.data or []

    async def add_user_memory(
        self, user_id: str, fact_content: str, category: str = "general",
        embedding: Optional[List[float]] = None, confidence_score: float = 1.0
    ) -> Dict[str, Any]:
        if not self.supabase:
            return {}
        payload = {
            "user_id": user_id,
            "category": category,
            "fact_content": fact_content,
            "confidence_score": confidence_score
        }
        if embedding:
            payload["embedding"] = embedding
        res = await asyncio.to_thread(
            lambda: self.supabase.table("user_memories").insert(payload).execute()
        )
        return res.data[0] if res.data else payload

db_helper = DatabaseHelper()
