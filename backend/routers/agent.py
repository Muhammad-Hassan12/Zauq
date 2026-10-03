"""Agent status and tool discovery router for Zauq v4.

Provides administrative and discovery endpoints:
- GET /api/agent/status: Runtime flags, step budgets, search provider, and MCP connectivity
- GET /api/agent/tools: List registered tools with guild scoping, risk levels, and origin
"""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from backend.config import settings
from backend.tools.registry import tool_registry
from backend.mcp_client.manager import mcp_manager

logger = logging.getLogger("zauq.routers.agent")

router = APIRouter(prefix="/api/agent", tags=["Agent"])


@router.get("/status")
async def get_agent_status() -> Dict[str, Any]:
    """Returns high-level runtime status, configuration limits, and subsystem health."""
    mcp_status = mcp_manager.get_status()
    servers = mcp_status.get("servers", [])
    connected_mcp = len([s for s in servers if s.get("connected")])

    all_tools = tool_registry.list_tools(enabled_only=True)

    return {
        "status": "online",
        "agent_runtime_enabled": settings.AGENT_RUNTIME_ENABLED,
        "max_tool_steps": settings.AGENT_MAX_TOOL_STEPS,
        "deep_max_tool_steps": settings.AGENT_DEEP_MAX_TOOL_STEPS,
        "web_search_provider": settings.WEB_SEARCH_PROVIDER,
        "auto_code_test_default": settings.AUTO_CODE_TEST_DEFAULT,
        "auto_code_repair_attempts": settings.AUTO_CODE_REPAIR_ATTEMPTS,
        "mcp_enabled": settings.MCP_ENABLED,
        "mcp_servers_connected": connected_mcp,
        "mcp_servers_total": len(servers),
        "total_tools": len(all_tools),
    }


@router.get("/tools")
async def list_agent_tools(
    guild_id: Optional[str] = Query(default=None, description="Optional Discord guild ID to filter guild-scoped tools"),
    include_schema: bool = Query(default=False, description="Whether to include JSON schemas (default false for clean summaries)"),
) -> List[Dict[str, Any]]:
    """Returns all enabled tools, optionally filtered by Discord guild scope."""
    tools = tool_registry.list_tools(enabled_only=True)

    if guild_id:
        tools = [
            t for t in tools
            if not t.allowed_guild_ids or guild_id in t.allowed_guild_ids
        ]

    result = []
    for t in tools:
        item: Dict[str, Any] = {
            "name": t.name,
            "description": t.description,
            "risk": t.risk,
            "source": t.source,
            "timeout_seconds": t.timeout_seconds,
            "enabled": t.enabled,
        }
        if t.server_id:
            item["server_id"] = t.server_id
        if include_schema:
            item["input_schema"] = t.input_schema
        result.append(item)

    return result
