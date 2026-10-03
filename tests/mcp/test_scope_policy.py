"""Tests for MCP access scoping, guild policies, and security invariants."""

import pytest
from backend.tools.base import ToolSpec
from backend.tools.policy import ToolPolicy, PolicyDecision
from backend.tools.registry import ToolRegistry
from backend.tools.executor import ToolExecutor
from backend.agent.capability_router import CapabilityRouter


def test_tool_policy_guild_scoping():
    policy = ToolPolicy()

    scoped_spec = ToolSpec(
        name="mcp.github.read_repo",
        description="Read repo",
        input_schema={},
        source="mcp",
        risk="read",
        allowed_guild_ids=["authorized_guild_123"],
    )

    unscoped_spec = ToolSpec(
        name="web.search",
        description="Public search",
        input_schema={},
        source="native",
        risk="read",
    )

    # Authorized guild
    assert policy.evaluate(scoped_spec, guild_id="authorized_guild_123") == PolicyDecision.ALLOW

    # Unauthorized guild
    assert policy.evaluate(scoped_spec, guild_id="unauthorized_guild_999") == PolicyDecision.DENY

    # Missing guild ID on scoped tool
    assert policy.evaluate(scoped_spec, guild_id=None) == PolicyDecision.DENY

    # Unscoped tool allows any guild
    assert policy.evaluate(unscoped_spec, guild_id="any_guild") == PolicyDecision.ALLOW
    assert policy.evaluate(unscoped_spec, guild_id=None) == PolicyDecision.ALLOW


def test_tool_policy_blocks_mcp_write_and_destructive():
    policy = ToolPolicy()

    write_tool = ToolSpec(
        name="mcp.github.create_issue",
        description="Create issue",
        input_schema={},
        source="mcp",
        risk="write",
        allowed_guild_ids=["guild_123"],
    )

    destructive_tool = ToolSpec(
        name="mcp.github.delete_branch",
        description="Delete branch",
        input_schema={},
        source="mcp",
        risk="destructive",
        allowed_guild_ids=["guild_123"],
    )

    # Phase 7: write/destructive tools require confirmation before execution
    assert policy.evaluate(write_tool, guild_id="guild_123", is_approved=False) == PolicyDecision.REQUIRE_CONFIRMATION
    assert policy.evaluate(destructive_tool, guild_id="guild_123", is_approved=False) == PolicyDecision.REQUIRE_CONFIRMATION

    # When approved, execution is allowed
    assert policy.evaluate(write_tool, guild_id="guild_123", is_approved=True) == PolicyDecision.ALLOW

    # When guild is unauthorized, it is DENIED even before confirmation
    assert policy.evaluate(write_tool, guild_id="unauthorized_guild") == PolicyDecision.DENY


@pytest.mark.asyncio
async def test_tool_executor_enforces_guild_scope():
    registry = ToolRegistry()
    policy = ToolPolicy()
    executor = ToolExecutor(registry, policy)

    spec = ToolSpec(
        name="mcp.docs.read_manual",
        description="Read private manual",
        input_schema={},
        source="mcp",
        risk="read",
        allowed_guild_ids=["vip_guild"],
    )

    async def _manual_handler(args):
        return "Secret Manual Content"

    registry.register(spec, _manual_handler)

    # Call with unauthorized guild
    result_fail = await executor.execute(
        "mcp.docs.read_manual",
        {},
        guild_id="public_guild",
    )
    assert result_fail.success is False
    assert "denied by policy" in result_fail.error.lower()

    # Call with authorized guild
    result_ok = await executor.execute(
        "mcp.docs.read_manual",
        {},
        guild_id="vip_guild",
    )
    assert result_ok.success is True
    assert result_ok.content == "Secret Manual Content"


def test_capability_router_guild_filter():
    registry = ToolRegistry()
    router = CapabilityRouter(registry=registry)

    github_scoped = ToolSpec(
        name="github.search_code",
        description="Search code",
        input_schema={},
        source="mcp",
        risk="read",
        allowed_guild_ids=["dev_guild"],
    )

    async def _dummy_handler(args):
        return ""

    registry.register(github_scoped, _dummy_handler)

    messages = [{"role": "user", "content": "Please check github pr and repo"}]

    # Selected for dev_guild
    tools_allowed = router.select_tools(
        messages=messages,
        provider="gemini",
        model_name="gemini-2.5-flash",
        guild_id="dev_guild",
    )
    assert any(t.name == "github.search_code" for t in tools_allowed)

    # Excluded for public_guild
    tools_denied = router.select_tools(
        messages=messages,
        provider="gemini",
        model_name="gemini-2.5-flash",
        guild_id="public_guild",
    )
    assert not any(t.name == "github.search_code" for t in tools_denied)
