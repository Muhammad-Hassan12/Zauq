from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from backend.memory.metrics import get_metrics_summary
from backend.memory.db import db_helper

router = APIRouter(prefix="/api/admin", tags=["Admin & Privacy"])

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
        res = db_helper.supabase.table("user_memories").delete().eq("user_id", user_id).execute()
        count = len(res.data) if res.data else 0
        return {
            "status": "success",
            "user_id": user_id,
            "deleted_memories_count": count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Purge Error: {str(e)}")
