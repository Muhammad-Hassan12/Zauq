"""Tests for MCP ToolAdapter, ToolSpec conversion, and execution handlers."""

import pytest
from unittest.mock import AsyncMock
from backend.mcp_client.adapter import mcp_tool_to_spec, create_mcp_handler, format_mcp_result
from backend.mcp_client.models import MCPServerConfig


class DummyMCPTool:
    def __init__(self, name: str, description: str, input_schema: dict):
        self.name = name
        self.description = description
        self.input_schema = input_schema


class DummyTextContent:
    def __init__(self, text: str):
        self.text = text


class DummyCallToolResult:
    def __init__(self, content=None, structured_content=None, is_error=False):
        self.content = content
        self.structured_content = structured_content
        self.is_error = is_error


@pytest.mark.asyncio
async def test_mcp_tool_to_spec_conversion():
    server_cfg = MCPServerConfig(
        id="github",
        transport="streamable_http",
        url="https://mcp.github.com",
        default_risk="read",
        timeout_seconds=12.0,
        allowed_guild_ids=["guild_123"],
        tool_risks={"create_pr": "write"},
    )

    mock_call_tool = AsyncMock()

    tool1 = DummyMCPTool(
        name="search_repos",
        description="Search GitHub repositories",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    tool2 = DummyMCPTool(
        name="create_pr",
        description="Create pull request",
        input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
    )

    spec1 = mcp_tool_to_spec(tool1, server_cfg, mock_call_tool)
    spec2 = mcp_tool_to_spec(tool2, server_cfg, mock_call_tool)

    # Verify tool 1
    assert spec1.name == "mcp.github.search_repos"
    assert spec1.description == "Search GitHub repositories"
    assert spec1.source == "mcp"
    assert spec1.server_id == "github"
    assert spec1.original_tool_name == "search_repos"
    assert spec1.risk == "read"
    assert spec1.timeout_seconds == 12.0
    assert spec1.allowed_guild_ids == ["guild_123"]

    # Verify tool 2 risk override
    assert spec2.name == "mcp.github.create_pr"
    assert spec2.risk == "write"
    assert spec2.original_tool_name == "create_pr"


@pytest.mark.asyncio
async def test_create_mcp_handler_execution():
    mock_call_tool = AsyncMock(
        return_value=DummyCallToolResult(
            content=[DummyTextContent("Repo: Zauq (Stars: 100)")]
        )
    )

    handler = create_mcp_handler(mock_call_tool, "search_repos")
    result = await handler({"query": "zauq"})

    mock_call_tool.assert_awaited_once_with("search_repos", {"query": "zauq"})
    assert result == "Repo: Zauq (Stars: 100)"


@pytest.mark.asyncio
async def test_create_mcp_handler_error_raises():
    mock_call_tool = AsyncMock(
        return_value=DummyCallToolResult(
            content=[DummyTextContent("Authentication failed: invalid token")],
            is_error=True,
        )
    )

    handler = create_mcp_handler(mock_call_tool, "list_orgs")
    with pytest.raises(RuntimeError, match="MCP tool reported error"):
        await handler({})


def test_format_mcp_result_structured():
    res = DummyCallToolResult(structured_content={"total_count": 42, "items": ["a", "b"]})
    out = format_mcp_result(res)
    assert out == {"total_count": 42, "items": ["a", "b"]}
