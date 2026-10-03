"""Health and status endpoint for Zauq v4 MCP Client Layer."""

from __future__ import annotations
from typing import Any
from fastapi import APIRouter
from backend.mcp_client.manager import mcp_manager
from backend.mcp_client.models import MCPHealthResponse

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/status", response_model=MCPHealthResponse)
async def get_mcp_status() -> dict[str, Any]:
    """Return health and connection status for all configured MCP servers.

    Returns:
        MCPHealthResponse containing enabled state and list of servers with
        connection status and tool counts. Never reveals secrets or endpoints.
    """
    return mcp_manager.get_status()
