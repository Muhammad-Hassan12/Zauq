from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.sandbox.code_runner import execute_code

router = APIRouter(prefix="/api/sandbox", tags=["Code Sandbox"])

from backend.memory.db import db_helper

class CodeExecRequest(BaseModel):
    code: str
    language: Optional[str] = "python"
    timeout: Optional[float] = 5.0
    channel_id: Optional[str] = None

@router.post("/exec")
async def run_code(req: CodeExecRequest):
    if req.channel_id:
        channel_profile = await db_helper.get_channel_profile(req.channel_id)
        if channel_profile:
            mode = channel_profile.get("operating_mode", "hangout")
            allow_exec = channel_profile.get("allow_code_exec", False)
            if mode != "dev" and not allow_exec:
                raise HTTPException(
                    status_code=403,
                    detail="Code execution disabled in this channel. Switch channel mode to Dev Mode via '/mode mode:dev' to execute code."
                )

    try:
        result = await execute_code(
            code=req.code,
            language=req.language or "python",
            timeout=req.timeout or 5.0
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

