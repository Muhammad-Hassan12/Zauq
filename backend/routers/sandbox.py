"""Sandbox Router for Zauq.

Provides endpoints for:
- Manual code execution (/api/sandbox/exec) with strict permission checks
- Sandbox status and resource limits (/api/sandbox/status)
- Channel auto-code-test mode configuration (/api/sandbox/auto_mode)
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, Any

from backend.sandbox.code_runner import execute_code, get_sandbox_status
from backend.memory.db import db_helper

logger = logging.getLogger("zauq.sandbox")

router = APIRouter(prefix="/api/sandbox", tags=["Code Sandbox"])


class CodeExecRequest(BaseModel):
    code: str
    language: Optional[Literal["python", "javascript", "node", "js", "bash", "sh"]] = "python"
    timeout: Optional[float] = Field(default=8.0, ge=1.0, le=30.0)
    channel_id: Optional[str] = None


class AutoModeRequest(BaseModel):
    channel_id: str
    guild_id: Optional[str] = None
    auto_mode: Literal["off", "auto", "always"]


@router.get("/status")
async def sandbox_status() -> Dict[str, Any]:
    """Returns sandbox daemon availability, resource limits, and security configuration."""
    return await get_sandbox_status()


@router.post("/auto_mode")
async def update_auto_code_test_mode(req: AutoModeRequest) -> Dict[str, Any]:
    """Configures automatic code testing mode ('off', 'auto', 'always') for a channel."""
    try:
        res = await db_helper.set_channel_auto_code_test_mode(
            channel_id=req.channel_id,
            guild_id=req.guild_id or "dm",
            mode=req.auto_mode,
        )
        return {
            "status": "success",
            "channel_id": req.channel_id,
            "auto_code_test_mode": req.auto_mode,
            "data": res,
        }
    except Exception as e:
        logger.error(f"Error updating auto_code_test_mode: {e}")
        raise HTTPException(status_code=500, detail="Failed to update auto code test mode.")


@router.post("/exec")
async def run_code(req: CodeExecRequest):
    """Execute code in isolated Docker sandbox with strict permission enforcement."""
    # Fix permission semantics per v4: explicit allow_code_exec=False MUST win
    # Do not implicitly override false permission merely because channel is in Dev Mode
    if req.channel_id:
        channel_profile = await db_helper.get_channel_profile(req.channel_id)
        if channel_profile and not channel_profile.get("allow_code_exec", False):
            raise HTTPException(
                status_code=403,
                detail="Code execution is disabled for this channel. Enable allow_code_exec to run code.",
            )

    try:
        result = await execute_code(
            code=req.code,
            language=req.language or "python",
            timeout=req.timeout or 8.0,
        )
        return result
    except Exception as e:
        logger.error(f"Sandbox execution error: {e}")
        raise HTTPException(status_code=500, detail="Code execution sandbox error.")
