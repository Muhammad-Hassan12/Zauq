import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from backend.memory.metrics import get_metrics_summary
from backend.memory.db import db_helper

logger = logging.getLogger("zauq.admin")

router = APIRouter(prefix="/api/admin", tags=["Admin & Privacy"])

@router.get("/config")
async def get_admin_config(guild_id: str):
    """Returns guild configuration including admin_role_id and default models."""
    if not guild_id or guild_id == "dm":
        return {}
    config = await db_helper.get_guild_config(guild_id)
    return config or {}

class SetRoleRequest(BaseModel):
    guild_id: str
    role_id: Optional[str] = None

@router.post("/set_role")
async def set_admin_role(req: SetRoleRequest):
    """Sets or clears the designated admin/staff role for Zauq management."""
    if not req.guild_id or req.guild_id == "dm":
        raise HTTPException(status_code=400, detail="Valid guild_id is required.")
    res = await db_helper.upsert_guild_config(guild_id=req.guild_id, admin_role_id=req.role_id)
    return {"status": "success", "guild_id": req.guild_id, "admin_role_id": req.role_id, "data": res}

@router.get("/metrics")
async def get_metrics(guild_id: Optional[str] = Query(None)):
    try:
        summary = await get_metrics_summary(guild_id)
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Metrics Error: {str(e)}")

@router.delete("/purge_user_data")
async def purge_user_data(user_id: str):
    if not user_id:
        raise HTTPException(status_code=400, detail="User ID is required.")

    if not db_helper.supabase:
        return {"status": "success", "message": "No database attached. Nothing to delete."}

    try:
        res = await asyncio.to_thread(
            lambda: db_helper.supabase.table("user_memories").delete().eq("user_id", user_id).execute()
        )
        count = len(res.data) if res.data else 0
        return {
            "status": "success",
            "user_id": user_id,
            "deleted_memories_count": count
        }
    except Exception as e:
        logger.error(f"Purge error for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to purge user data. Please try again.")

@router.get("/memory_stats")
async def memory_stats(guild_id: Optional[str] = Query(None)):
    """Returns count of user memories and server lore entries, optionally filtered by guild."""
    if not db_helper.supabase:
        return {"user_memories": 0, "server_lore": 0, "source": "no_db"}

    try:
        import asyncio
        mem_query = lambda: db_helper.supabase.table("user_memories").select("memory_id", count="exact").execute()
        lore_query_builder = db_helper.supabase.table("server_lore").select("lore_id", count="exact")
        if guild_id:
            lore_query_builder = lore_query_builder.eq("guild_id", guild_id)
        lore_query = lambda: lore_query_builder.execute()

        mem_res = await asyncio.to_thread(mem_query)
        lore_res = await asyncio.to_thread(lore_query)

        return {
            "user_memories": mem_res.count if mem_res.count is not None else len(mem_res.data or []),
            "server_lore": lore_res.count if lore_res.count is not None else len(lore_res.data or []),
            "source": "supabase"
        }
    except Exception as e:
        logger.warning(f"Could not fetch memory stats: {e}")
        return {"user_memories": 0, "server_lore": 0, "source": "error", "detail": str(e)}

@router.get("/active_channels")
async def active_channels(guild_id: Optional[str] = Query(None)):
    """Returns channels that have configured profiles."""
    if not db_helper.supabase:
        return {"channels": [], "source": "no_db"}

    try:
        import asyncio
        query_builder = db_helper.supabase.table("channel_profiles").select("*")
        if guild_id:
            query_builder = query_builder.eq("guild_id", guild_id)
        query = lambda: query_builder.limit(50).execute()

        res = await asyncio.to_thread(query)
        return {
            "channels": res.data or [],
            "count": len(res.data or []),
            "source": "supabase"
        }
    except Exception as e:
        logger.warning(f"Could not fetch active channels: {e}")
        return {"channels": [], "source": "error", "detail": str(e)}

@router.get("/xp_leaderboard")
async def xp_leaderboard(guild_id: Optional[str] = Query(None), limit: int = Query(10)):
    """Returns server-wide XP leaderboard."""
    if not db_helper.supabase:
        return {"leaderboard": [], "source": "no_db"}

    try:
        import asyncio
        query_builder = db_helper.supabase.table("user_stats").select("*").order("xp", desc=True).limit(limit)
        if guild_id:
            query_builder = query_builder.eq("guild_id", guild_id)
        query = lambda: query_builder.execute()

        res = await asyncio.to_thread(query)
        return {
            "leaderboard": res.data or [],
            "count": len(res.data or []),
            "source": "supabase"
        }
    except Exception as e:
        logger.warning(f"Could not fetch XP leaderboard: {e}")
        return {"leaderboard": [], "source": "error", "detail": str(e)}
