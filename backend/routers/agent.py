"""Agent status and tool discovery router for Zauq v4."""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Literal
from backend.memory.db import db_helper
from backend.agent.rollout import feature_enabled

from backend.config import settings
from backend.tools.registry import tool_registry
from backend.mcp_client.manager import mcp_manager

logger = logging.getLogger("zauq.routers.agent")

router = APIRouter(prefix="/api/agent", tags=["Agent"])


@router.get("/status")
async def get_agent_status(channel_id: Optional[str] = None, guild_id: Optional[str] = None) -> Dict[str, Any]:
    """Returns high-level runtime status, configuration limits, and subsystem health."""
    mcp_status = mcp_manager.get_status()
    servers = mcp_status.get("servers", [])
    connected_mcp = len([s for s in servers if s.get("connected")])

    all_tools = tool_registry.list_tools(enabled_only=True)
    profile = await db_helper.get_channel_profile(channel_id) if channel_id else None
    guild = await db_helper.get_guild_config(guild_id) if guild_id else None

    return {
        "status": "online",
        "agent_runtime_enabled": feature_enabled('agent',channel_id,guild_id,profile,guild),
        'agent_master_enabled':settings.AGENT_RUNTIME_ENABLED,
        "max_tool_steps": min(max(0,settings.AGENT_MAX_TOOL_STEPS),8),
        "deep_max_tool_steps": min(max(0,settings.AGENT_DEEP_MAX_TOOL_STEPS),8),
        "web_search_provider": settings.WEB_SEARCH_PROVIDER,
        "auto_code_test_default": settings.AUTO_CODE_TEST_DEFAULT,
        'auto_code_test_mode':(profile or {}).get('auto_code_test_mode',settings.AUTO_CODE_TEST_DEFAULT),
        "auto_code_repair_attempts": settings.AUTO_CODE_REPAIR_ATTEMPTS,
        "mcp_enabled": feature_enabled('mcp',channel_id,guild_id,profile,guild),
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

    tools = [
            t for t in tools
            if t.allowed_guild_ids is None or (guild_id and guild_id in t.allowed_guild_ids)
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


class FeatureConfigRequest(BaseModel):
    feature: Literal['agent','mcp'] = 'agent'
    enabled: bool
    scope: Literal['channel','server'] = 'channel'
    channel_id: str | None = None
    guild_id: str | None = None


@router.post('/config')
async def configure_feature(req: FeatureConfigRequest):
    from fastapi import HTTPException
    if not db_helper.supabase:
        raise HTTPException(503,'A database is required to persist rollout controls')
    field='agent_runtime_enabled' if req.feature=='agent' else 'mcp_enabled'
    if req.scope=='server':
        if not req.guild_id or req.guild_id=='dm':
            raise HTTPException(400,'Server scope requires a guild')
        import asyncio
        await db_helper.upsert_guild_config(req.guild_id)
        payload={field:req.enabled}
        await asyncio.to_thread(lambda:db_helper.supabase.table('guild_configs').update(payload).eq('guild_id',req.guild_id).execute())
    else:
        if not req.channel_id:
            raise HTTPException(400,'Channel scope requires channel_id')
        profile=await db_helper.get_channel_profile(req.channel_id)
        if not profile:
            await db_helper.upsert_channel_profile(req.channel_id,req.guild_id or 'dm','hangout')
        import asyncio
        await asyncio.to_thread(lambda:db_helper.supabase.table('channel_profiles').update({field:req.enabled}).eq('channel_id',req.channel_id).execute())
    return {'status':'success','feature':req.feature,'scope':req.scope,'enabled':req.enabled,'master_enabled':settings.AGENT_RUNTIME_ENABLED if req.feature=='agent' else settings.MCP_ENABLED}
