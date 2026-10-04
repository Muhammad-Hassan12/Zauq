"""Unit tests for Agent Router (/api/agent/status and /api/agent/tools)."""

import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.tools.registry import tool_registry
from backend.tools.base import ToolSpec


from backend.config import settings

AUTH_HEADERS = {"X-Zauq-Token": settings.INTERNAL_API_KEY} if settings.INTERNAL_API_KEY else {}


@pytest.mark.asyncio
async def test_agent_status_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", headers=AUTH_HEADERS) as client:
        res = await client.get("/api/agent/status")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "online"
        assert "agent_runtime_enabled" in data
        assert "max_tool_steps" in data
        assert "deep_max_tool_steps" in data
        assert "web_search_provider" in data
        assert "auto_code_test_default" in data
        assert "mcp_enabled" in data
        assert "total_tools" in data
        assert isinstance(data["total_tools"], int)


@pytest.mark.asyncio
async def test_agent_tools_listing_and_guild_scoping():
    global_tool = ToolSpec(
        name="test.agent_global_tool",
        description="Global test tool for agent router",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        risk="read",
    )
    guild_tool = ToolSpec(
        name="test.agent_guild_tool",
        description="Guild-scoped test tool",
        input_schema={"type": "object"},
        risk="write",
        allowed_guild_ids=["guild_alpha"],
    )

    tool_registry.register(global_tool, handler=lambda x: None)
    tool_registry.register(guild_tool, handler=lambda x: None)

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test", headers=AUTH_HEADERS) as client:
            # 1. No guild query parameter -> all enabled tools
            res_all = await client.get("/api/agent/tools")
            assert res_all.status_code == 200
            tools_all = res_all.json()
            names_all = [t["name"] for t in tools_all]
            assert "test.agent_global_tool" in names_all
            assert "test.agent_guild_tool" not in names_all  # No guild context must not reveal scoped tools.

            # By default schemas are omitted for clean UX
            g_item = next(t for t in tools_all if t["name"] == "test.agent_global_tool")
            assert "input_schema" not in g_item
            assert g_item["risk"] == "read"

            # 2. include_schema=true -> schemas included
            res_schema = await client.get("/api/agent/tools?include_schema=true")
            assert res_schema.status_code == 200
            g_schema_item = next(t for t in res_schema.json() if t["name"] == "test.agent_global_tool")
            assert "input_schema" in g_schema_item
            assert "properties" in g_schema_item["input_schema"]

            # 3. Filter for authorized guild_alpha
            res_alpha = await client.get("/api/agent/tools?guild_id=guild_alpha")
            assert res_alpha.status_code == 200
            names_alpha = [t["name"] for t in res_alpha.json()]
            assert "test.agent_global_tool" in names_alpha
            assert "test.agent_guild_tool" in names_alpha

            # 4. Filter for unauthorized guild_beta
            res_beta = await client.get("/api/agent/tools?guild_id=guild_beta")
            assert res_beta.status_code == 200
            names_beta = [t["name"] for t in res_beta.json()]
            assert "test.agent_global_tool" in names_beta
            assert "test.agent_guild_tool" not in names_beta
    finally:
        tool_registry.unregister("test.agent_global_tool")
        tool_registry.unregister("test.agent_guild_tool")
