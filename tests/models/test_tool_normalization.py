"""Tests for Tool Normalization and Schema Conversion across Providers."""

import pytest
from backend.agent.types import ToolCall, ToolCallBatch, ToolResultMessage, AgentModelTurn
from backend.tools.base import ToolSpec
from backend.models.tool_schemas import (
    to_gemini_tools,
    to_anthropic_tools,
    to_openai_tools,
    normalize_tool_call_name,
)


@pytest.fixture
def sample_tool_spec():
    return ToolSpec(
        name="web.search",
        description="Search the web for up-to-date information.",
        input_schema={
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {"type": "integer", "description": "Max results to return"}
            },
            "required": ["query"]
        }
    )


class TestToolNormalization:
    def test_to_gemini_tools(self, sample_tool_spec):
        gemini_tools = to_gemini_tools([sample_tool_spec])
        assert len(gemini_tools) == 1
        assert "functionDeclarations" in gemini_tools[0]

        decl = gemini_tools[0]["functionDeclarations"][0]
        assert decl["name"] == "web__search"
        assert decl["description"] == sample_tool_spec.description
        # Verify schema cleaned for Gemini
        assert "$schema" not in decl["parameters"]
        assert decl["parameters"]["type"] == "OBJECT"
        assert "query" in decl["parameters"]["properties"]
        assert decl["parameters"]["properties"]["query"]["type"] == "STRING"

    def test_to_anthropic_tools(self, sample_tool_spec):
        anthropic_tools = to_anthropic_tools([sample_tool_spec])
        assert len(anthropic_tools) == 1
        tool = anthropic_tools[0]
        assert tool["name"] == "web__search"
        assert tool["description"] == sample_tool_spec.description
        assert "input_schema" in tool
        assert "query" in tool["input_schema"]["properties"]

    def test_to_openai_tools(self, sample_tool_spec):
        openai_tools = to_openai_tools([sample_tool_spec])
        assert len(openai_tools) == 1
        tool = openai_tools[0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "web__search"
        assert tool["function"]["description"] == sample_tool_spec.description
        assert "parameters" in tool["function"]

    def test_normalize_tool_call_name(self):
        assert normalize_tool_call_name("web__search") == "web.search"
        assert normalize_tool_call_name("github__search_code") == "github.search_code"
        assert normalize_tool_call_name("calculator") == "calculator"

    def test_agent_model_turn_properties(self):
        turn_with_tools = AgentModelTurn(
            text="Thinking about this...",
            tool_calls=[ToolCall(id="call_1", name="web.search", arguments={"query": "test"})]
        )
        assert turn_with_tools.has_tool_calls is True
        assert turn_with_tools.is_final_answer is False

        turn_final = AgentModelTurn(
            text="Here is your answer.",
            tool_calls=[]
        )
        assert turn_final.has_tool_calls is False
        assert turn_final.is_final_answer is True

    def test_tool_result_message(self):
        msg = ToolResultMessage(
            tool_call_id="call_123",
            tool_name="web.search",
            content="Search results text",
            is_error=False
        )
        assert msg.tool_call_id == "call_123"
        assert msg.name == "web.search"
        assert msg.tool_name == "web.search"
        assert msg.content == "Search results text"
        assert msg.is_error is False
