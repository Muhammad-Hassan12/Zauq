import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal
from backend.sandbox.code_runner import execute_code
from backend.memory.db import db_helper

logger = logging.getLogger("zauq.sandbox")

router = APIRouter(prefix="/api/sandbox", tags=["Code Sandbox"])

class CodeExecRequest(BaseModel):
    code: str
    language: Optional[Literal["python", "javascript", "node", "js", "bash", "sh"]] = "python"
    timeout: Optional[float] = Field(default=5.0, ge=1.0, le=30.0)
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
        logger.error(f"Sandbox execution error: {e}")
        raise HTTPException(status_code=500, detail="Code execution sandbox error.")

