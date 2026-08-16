import asyncio
import hashlib
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.moderation.content_filter import content_filter
from backend.memory.db import db_helper

router = APIRouter(prefix="/api/moderation", tags=["Moderation"])

class ModerationCheckRequest(BaseModel):
    guild_id: str
    channel_id: str
    user_id: str
    message_content: str

class ModerationSettingsRequest(BaseModel):
    guild_id: str
    enabled: bool
    sensitivity: Optional[str] = "medium"

@router.post("/check")
async def check_content(req: ModerationCheckRequest):
    # Fetch guild moderation settings
    guild_config = await db_helper.get_guild_config(req.guild_id)
    enabled = guild_config.get("moderation_enabled", False) if guild_config else False
    sensitivity = guild_config.get("moderation_sensitivity", "medium") if guild_config else "medium"

    if not enabled:
        return {"enabled": False, "action": "none", "classification": "safe"}

    result = await content_filter.check_message(req.message_content, sensitivity=sensitivity)
    classification = result.get("classification", "safe")

    if classification != "safe" and db_helper.supabase:
        action = "deleted" if classification == "toxic" else "flagged"
        # Store only a content hash — never persist raw toxic message text
        content_hash = hashlib.sha256(req.message_content[:500].encode()).hexdigest()[:32]
        payload = {
            "guild_id": req.guild_id,
            "channel_id": req.channel_id,
            "user_id": req.user_id,
            "message_content": f"[hash:{content_hash}]",
            "action_taken": action,
            "severity": result.get("severity", "low"),
            "reason": result.get("reason", "Automated AI content filter")
        }
        await asyncio.to_thread(
            lambda: db_helper.supabase.table("moderation_log").insert(payload).execute()
        )

    return {
        "enabled": True,
        "classification": classification,
        "reason": result.get("reason", ""),
        "severity": result.get("severity", "low"),
        "action": "delete" if classification == "toxic" else ("flag" if classification == "borderline" else "none")
    }

@router.post("/settings")
async def update_moderation_settings(req: ModerationSettingsRequest):
    if not db_helper.supabase:
        return {"status": "success"}

    payload = {
        "guild_id": req.guild_id,
        "guild_name": f"Guild {req.guild_id}",
        "moderation_enabled": req.enabled,
        "moderation_sensitivity": req.sensitivity or "medium"
    }

    res = await asyncio.to_thread(
        lambda: db_helper.supabase.table("guild_configs").upsert(payload).execute()
    )
    return {"status": "success", "data": res.data}

@router.get("/log")
async def get_moderation_log(guild_id: str, limit: int = 10):
    if not db_helper.supabase:
        return {"logs": []}

    res = await asyncio.to_thread(
        lambda: db_helper.supabase.table("moderation_log")
            .select("*")
            .eq("guild_id", guild_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
    )
    return {"logs": res.data or []}
