import logging
from fastapi import APIRouter, HTTPException
from typing import Optional
from backend.games.trivia import generate_trivia_question

logger = logging.getLogger("zauq.trivia")

router = APIRouter(prefix="/api/games", tags=["Mini-Games"])

@router.get("/trivia")
async def get_trivia_question(guild_id: Optional[str] = "global"):
    try:
        data = await generate_trivia_question(guild_id or "global")
        return data
    except Exception as e:
        logger.error(f"Trivia generation error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate trivia question.")
