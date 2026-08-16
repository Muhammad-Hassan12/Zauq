import asyncio
import datetime
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from backend.memory.db import db_helper

logger = logging.getLogger("zauq.reminders")

router = APIRouter(prefix="/api/reminders", tags=["Reminders"])

class CreateReminderRequest(BaseModel):
    guild_id: str
    channel_id: str
    user_id: str
    message: str
    in_minutes: int

@router.post("/create")
async def create_reminder(req: CreateReminderRequest):
    if not db_helper.supabase:
        raise HTTPException(status_code=500, detail="Database not attached.")

    if req.in_minutes < 1 or req.in_minutes > 10080:  # Max 7 days
        raise HTTPException(status_code=400, detail="in_minutes must be between 1 and 10,080 (7 days).")

    try:
        remind_dt = (datetime.datetime.utcnow() + datetime.timedelta(minutes=req.in_minutes)).isoformat()
        payload = {
            "guild_id": req.guild_id,
            "channel_id": req.channel_id,
            "user_id": req.user_id,
            "message": req.message,
            "remind_at": remind_dt,
            "delivered": False
        }
        res = await asyncio.to_thread(
            lambda: db_helper.supabase.table("scheduled_reminders").insert(payload).execute()
        )
        return {"status": "success", "in_minutes": req.in_minutes, "data": res.data[0] if res.data else payload}
    except Exception as e:
        logger.error(f"Failed to create reminder: {e}")
        raise HTTPException(status_code=500, detail="Failed to create reminder.")

@router.get("/pending")
async def get_pending_reminders():
    if not db_helper.supabase:
        return {"reminders": []}

    try:
        now_str = datetime.datetime.utcnow().isoformat()
        res = await asyncio.to_thread(
            lambda: db_helper.supabase.table("scheduled_reminders")
                .select("*")
                .lte("remind_at", now_str)
                .eq("delivered", False)
                .limit(20)
                .execute()
        )
        return {"reminders": res.data or []}
    except Exception as e:
        logger.error(f"Failed to fetch pending reminders: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch pending reminders.")

@router.post("/mark_delivered")
async def mark_reminder_delivered(reminder_id: str = Query(...)):
    if not db_helper.supabase:
        return {"status": "success"}

    try:
        res = await asyncio.to_thread(
            lambda: db_helper.supabase.table("scheduled_reminders")
                .update({"delivered": True})
                .eq("reminder_id", reminder_id)
                .execute()
        )
        return {"status": "success", "data": res.data}
    except Exception as e:
        logger.error(f"Failed to mark reminder as delivered: {e}")
        raise HTTPException(status_code=500, detail="Failed to update reminder status.")
