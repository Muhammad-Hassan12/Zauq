import logging
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from backend.memory.xp import xp_manager

logger = logging.getLogger("zauq.xp")

router = APIRouter(prefix="/api/xp", tags=["XP System"])

_VALID_STAT_TYPES = {"message", "command", "trivia_correct", "trivia_played"}

@router.post("/award")
async def award_user_xp(user_id: str, guild_id: str, display_name: Optional[str] = None, xp: int = 1, stat_type: str = "message"):
    # Clamp XP to valid range to prevent manipulation
    xp = min(max(xp, 1), 10)
    if stat_type not in _VALID_STAT_TYPES:
        stat_type = "message"
    try:
        res = await xp_manager.award_xp(user_id, guild_id, display_name, xp, stat_type)
        return {"status": "success", "data": res}
    except Exception as e:
        logger.error(f"XP award error: {e}")
        raise HTTPException(status_code=500, detail="XP award failed.")

@router.get("/rank")
async def get_rank(user_id: str, guild_id: Optional[str] = "global"):
    try:
        data = await xp_manager.get_user_rank(user_id, guild_id or "global")
        return data
    except Exception as e:
        logger.error(f"Get rank error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch user rank.")

@router.get("/leaderboard")
async def get_leaderboard(guild_id: Optional[str] = "global", limit: int = 10):
    try:
        leaders = await xp_manager.get_leaderboard(guild_id or "global", limit)
        return {"leaderboard": leaders}
    except Exception as e:
        logger.error(f"Get leaderboard error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch leaderboard.")
