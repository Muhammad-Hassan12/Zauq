"""API Router for Phase 7 Human-in-the-Loop Side-Effect Actions."""

import logging
from typing import Any
from fastapi import APIRouter, HTTPException, Depends
from backend.actions.models import (
    PendingAction,
    ActionCreateRequest,
    ActionApproveRequest,
    ActionDenyRequest,
)
from backend.actions.service import action_service
from backend.tools.executor import ToolExecutor
from backend.tools.registry import tool_registry
from backend.tools.policy import ToolPolicy

logger = logging.getLogger("zauq.routers.actions")

router = APIRouter(prefix="/api/actions", tags=["actions"])

# Shared default executor for approved action execution
_executor = ToolExecutor(tool_registry, ToolPolicy())


@router.post("/create", response_model=PendingAction)
async def create_action(req: ActionCreateRequest) -> PendingAction:
    """Stage a new pending action requiring human confirmation."""
    return await action_service.create_action(
        channel_id=req.channel_id,
        user_id=req.user_id,
        tool_name=req.tool_name,
        arguments=req.arguments,
        guild_id=req.guild_id,
        risk=req.risk,
        ttl_seconds=req.ttl_seconds,
    )


@router.get("/{action_id}", response_model=PendingAction)
async def get_action(action_id: str) -> PendingAction:
    """Fetch status and details of a pending action."""
    action = await action_service.get_action(action_id)
    if not action:
        raise HTTPException(status_code=404, detail=f"Action '{action_id}' not found.")
    return action


@router.post("/{action_id}/approve")
async def approve_and_execute_action(
    action_id: str,
    req: ActionApproveRequest,
) -> dict[str, Any]:
    """Approve and execute a staged action (single-use)."""
    try:
        approved_action = await action_service.approve_action(
            action_id=action_id,
            user_id=req.user_id,
            signature=req.signature,
            is_admin=req.is_admin,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Action not found.")
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

    # Execute the action immediately upon valid approval
    tool_result = await action_service.execute_approved_action(action_id, _executor)

    return {
        "action": approved_action.model_dump(),
        "execution": {
            "success": tool_result.success,
            "content": tool_result.content,
            "error": tool_result.error,
            "duration_ms": tool_result.duration_ms,
        }
    }


@router.post("/{action_id}/deny")
async def deny_action(
    action_id: str,
    req: ActionDenyRequest,
) -> dict[str, Any]:
    """Deny a staged action."""
    try:
        denied_action = await action_service.deny_action(
            action_id=action_id,
            user_id=req.user_id,
            is_admin=req.is_admin,
        )
        return {"action": denied_action.model_dump(), "status": "denied"}
    except KeyError:
        raise HTTPException(status_code=404, detail="Action not found.")
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
