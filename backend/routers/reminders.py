import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from backend.memory.db import db_helper

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
        # Calculate remind_at timestamp in Supabase
        res = await asyncio.to_thread(
            lambda: db_helper.supabase.rpc(
                "create_reminder_helper", # Or raw insert with NOW() + interval
            ).execute() if hasattr(db_helper.supabase, "rpc_create_reminder") else None
        )
        
        # Raw insert
        payload = {
            "guild_id": req.guild_id,
            "channel_id": req.channel_id,
            "user_id": req.user_id,
            "message": req.message,
            "remind_at": f"now() + interval '{req.in_minutes} minutes'",
            "delivered": False
        }

        # Use supabase insert
        res = await asyncio.to_thread(
            lambda: db_helper.supabase.table("scheduled_reminders").insert({
                "guild_id": req.guild_id,
                "channel_id": req.channel_id,
                "user_id": req.user_id,
                "message": req.message,
                "delivered": False
            }).execute()
        )
        
        # Update remind_at via RPC or post-update
        if res.data:
            rem_id = res.data[0]["reminder_id"]
            await asyncio.to_thread(
                lambda: db_helper.supabase.rpc("set_reminder_time", {"r_id": rem_id, "mins": req.in_minutes}).execute()
                if hasattr(db_helper.supabase, "rpc") else None
            )

        return {"status": "success", "in_minutes": req.in_minutes, "data": res.data[0] if res.data else {}}
    except Exception as e:
        # Direct SQL string payload fallback
        try:
            import datetime
            remind_dt = (datetime.datetime.utcnow() + datetime.timedelta(minutes=req.in_minutes)).isoformat()
            raw_payload = {
                "guild_id": req.guild_id,
                "channel_id": req.channel_id,
                "user_id": req.user_id,
                "message": req.message,
                "remind_at": remind_dt,
                "delivered": False
            }
            res = await asyncio.to_thread(
                lambda: db_helper.supabase.table("scheduled_reminders").insert(raw_payload).execute()
            )
            return {"status": "success", "in_minutes": req.in_minutes, "data": res.data[0] if res.data else raw_payload}
        except Exception as inner_err:
            raise HTTPException(status_code=500, detail=str(inner_err))

@router.get("/pending")
async def get_pending_reminders():
    if not db_helper.supabase:
        return {"reminders": []}

    try:
        import datetime
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
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mark_delivered")
async def mark_reminder_delivered(reminder_id: str):
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
        raise HTTPException(status_code=500, detail=str(e))
