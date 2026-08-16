import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.memory.rag import add_server_lore, search_server_lore

logger = logging.getLogger("zauq.rag")

router = APIRouter(prefix="/api/lore", tags=["Server Lore"])

class AddLoreRequest(BaseModel):
    guild_id: str
    source_type: Optional[str] = "inside_joke"
    content: str

@router.post("/add")
async def create_lore(req: AddLoreRequest):
    try:
        res = await add_server_lore(req.guild_id, req.source_type or "inside_joke", req.content)
        return {"status": "success", "data": res}
    except Exception as e:
        logger.error(f"Failed to add server lore: {e}")
        raise HTTPException(status_code=500, detail="Failed to add server lore.")

@router.get("/search")
async def search_lore(guild_id: str, query: str, limit: int = 3):
    try:
        results = await search_server_lore(guild_id, query, top_k=limit)
        return {"results": results}
    except Exception as e:
        logger.error(f"Failed to search server lore: {e}")
        raise HTTPException(status_code=500, detail="Failed to search server lore.")
