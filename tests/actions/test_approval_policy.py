"""Tests for ToolPolicy human-in-the-loop decisions and ToolExecutor integration."""

import pytest
from backend.tools.base import ToolSpec
from backend.tools.policy import ToolPolicy, PolicyDecision
from backend.tools.registry import ToolRegistry
from backend.tools.executor import ToolExecutor


def test_tool_policy_write_and_destructive_transitions():
    policy = ToolPolicy()

    read_spec = ToolSpec(name="web.search", description="Search", input_schema={}, risk="read")
    write_spec = ToolSpec(name="github.create_pr", description="PR", input_schema={}, risk="write")
    destructive_spec = ToolSpec(name="db.drop_table", description="Drop", input_schema={}, risk="destructive")
    disabled_spec = ToolSpec(name="github.create_pr", description="PR", input_schema={}, risk="write", enabled=False)

    # 1. Read tools are always frictionless (ALLOW)
    assert policy.evaluate(read_spec, is_approved=False) == PolicyDecision.ALLOW

    # 2. Write tools without approval -> REQUIRE_CONFIRMATION
    assert policy.evaluate(write_spec, is_approved=False) == PolicyDecision.REQUIRE_CONFIRMATION

    # 3. Write tools with explicit human approval -> ALLOW
    assert policy.evaluate(write_spec, is_approved=True) == PolicyDecision.ALLOW

    # 4. Destructive tools without approval -> REQUIRE_CONFIRMATION
    assert policy.evaluate(destructive_spec, is_approved=False) == PolicyDecision.REQUIRE_CONFIRMATION

    # 5. Destructive tools with explicit human approval -> ALLOW
    assert policy.evaluate(destructive_spec, is_approved=True) == PolicyDecision.ALLOW

    # 6. Disabled tools are always DENIED even if marked approved
    assert policy.evaluate(disabled_spec, is_approved=True) == PolicyDecision.DENY


@pytest.mark.asyncio
async def test_tool_executor_confirmation_required_flow():
    registry = ToolRegistry()
    policy = ToolPolicy()
    executor = ToolExecutor(registry, policy)

    async def mock_write(args):
        return "File saved."

    write_tool = ToolSpec(
        name="fs.write_file",
        description="Write file to disk",
        input_schema={},
        source="mcp",
        risk="write",
    )
    registry.register(write_tool, mock_write)

    # Step 1: Execute unapproved -> returns REQUIRES_CONFIRMATION
    res_staged = await executor.execute("fs.write_file", {"path": "test.txt", "content": "hi"}, is_approved=False)
    assert res_staged.success is False
    assert res_staged.error == "REQUIRES_CONFIRMATION"
    assert res_staged.metadata.get("requires_confirmation") is True

    # Step 2: Execute with approval -> executes handler
    res_approved = await executor.execute("fs.write_file", {"path": "test.txt", "content": "hi"}, is_approved=True)
    assert res_approved.success is True
    assert res_approved.content == "File saved."
