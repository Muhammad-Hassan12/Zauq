"""Tests for Tool Calling with OpenAI-Compatible Adapters and Anthropic Claude."""

import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from backend.models.openai_compatible_client import OpenAICompatibleClient
from backend.models.anthropic_client import AnthropicClient
from backend.models.qwen_client import QwenClient
from backend.models.deepseek_client import DeepSeekClient
from backend.agent.types import ToolCall, ToolResultMessage, AgentModelTurn
from backend.tools.base import ToolSpec


@pytest.fixture
def sample_tool():
    return ToolSpec(
        name="web.search",
        description="Search online web pages",
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"]
        }
    )


class TestOpenAICompatibleTools:
    @pytest.mark.asyncio
    async def test_openai_compatible_returns_tool_call(self, sample_tool):
        client = OpenAICompatibleClient(base_url="https://api.openai.test/v1", api_key="test_key")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_123",
                                "type": "function",
                                "function": {
                                    "name": "web__search",
                                    "arguments": json.dumps({"query": "python 3.12 features"})
                                }
                            }
                        ]
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            turn = await client.generate_agent_turn(
                messages=[{"role": "user", "content": "Search python features"}],
                tools=[sample_tool]
            )

            assert isinstance(turn, AgentModelTurn)
            assert turn.has_tool_calls is True
            assert len(turn.tool_calls) == 1
            call = turn.tool_calls[0]
            assert call.id == "call_123"
            assert call.name == "web.search"
            assert call.arguments == {"query": "python 3.12 features"}

    @pytest.mark.asyncio
    async def test_openai_compatible_serializes_tool_result(self, sample_tool):
        client = OpenAICompatibleClient(base_url="https://api.openai.test/v1", api_key="test_key")
        messages = [
            {"role": "user", "content": "Search python"},
            {
                "role": "assistant",
                "tool_calls": [ToolCall(id="call_123", name="web.search", arguments={"query": "python"})]
            },
            ToolResultMessage(
                tool_call_id="call_123",
                tool_name="web.search",
                content="Python 3.12 released.",
                is_error=False
            )
        ]

        formatted = client._format_messages(messages)
        assert len(formatted) == 3
        # Check tool result formatted as role="tool"
        tool_turn = formatted[2]
        assert tool_turn["role"] == "tool"
        assert tool_turn["tool_call_id"] == "call_123"
        assert tool_turn["name"] == "web__search"
        assert tool_turn["content"] == "Python 3.12 released."


class TestAnthropicTools:
    @pytest.mark.asyncio
    async def test_anthropic_returns_tool_call(self, sample_tool):
        client = AnthropicClient(api_key="sk-ant-test")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [
                {"type": "text", "text": "I will search the web for that."},
                {
                    "type": "tool_use",
                    "id": "toolu_abc456",
                    "name": "web__search",
                    "input": {"query": "Claude 3.7 features"}
                }
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            turn = await client.generate_agent_turn(
                messages=[{"role": "user", "content": "Search Claude features"}],
                tools=[sample_tool],
                model_name="claude-3-7-sonnet-latest"
            )

            assert isinstance(turn, AgentModelTurn)
            assert turn.has_tool_calls is True
            assert "I will search" in turn.text
            assert len(turn.tool_calls) == 1
            call = turn.tool_calls[0]
            assert call.id == "toolu_abc456"
            assert call.name == "web.search"
            assert call.arguments == {"query": "Claude 3.7 features"}

    @pytest.mark.asyncio
    async def test_anthropic_serializes_tool_result(self, sample_tool):
        client = AnthropicClient(api_key="sk-ant-test")
        messages = [
            {"role": "user", "content": "Search Claude"},
            {
                "role": "assistant",
                "tool_calls": [ToolCall(id="toolu_abc456", name="web.search", arguments={"query": "Claude"})]
            },
            ToolResultMessage(
                tool_call_id="toolu_abc456",
                tool_name="web.search",
                content="Claude is an LLM from Anthropic.",
                is_error=False
            )
        ]

        system, formatted = client._format_messages_and_system(messages)
        assert len(formatted) == 3

        # Assistant turn contains tool_use block
        assistant_turn = formatted[1]
        assert assistant_turn["role"] == "assistant"
        assert assistant_turn["content"][0]["type"] == "tool_use"
        assert assistant_turn["content"][0]["id"] == "toolu_abc456"

        # Tool result turn is user turn with tool_result block
        tool_turn = formatted[2]
        assert tool_turn["role"] == "user"
        assert tool_turn["content"][0]["type"] == "tool_result"
        assert tool_turn["content"][0]["tool_use_id"] == "toolu_abc456"
        assert tool_turn["content"][0]["content"] == "Claude is an LLM from Anthropic."


class TestQwenAndDeepSeekTools:
    @pytest.mark.asyncio
    async def test_qwen_agent_turn(self, sample_tool):
        client = QwenClient(api_key="sk-qwen", base_url="https://dashscope.aliyuncs.com")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "qwen_call_1",
                                "type": "function",
                                "function": {
                                    "name": "web__search",
                                    "arguments": json.dumps({"query": "Alibaba Cloud"})
                                }
                            }
                        ]
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            turn = await client.generate_agent_turn(
                messages=[{"role": "user", "content": "Search Alibaba"}],
                tools=[sample_tool],
                model_name="qwen-turbo"
            )

            assert isinstance(turn, AgentModelTurn)
            assert turn.has_tool_calls is True
            assert turn.tool_calls[0].name == "web.search"

    @pytest.mark.asyncio
    async def test_deepseek_agent_turn(self, sample_tool):
        client = DeepSeekClient(api_key="sk-deepseek")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "deepseek_call_1",
                                "type": "function",
                                "function": {
                                    "name": "web__search",
                                    "arguments": json.dumps({"query": "DeepSeek-V3 architecture"})
                                }
                            }
                        ]
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            turn = await client.generate_agent_turn(
                messages=[{"role": "user", "content": "Search DeepSeek V3"}],
                tools=[sample_tool],
                model_name="deepseek-chat"
            )

            assert isinstance(turn, AgentModelTurn)
            assert turn.has_tool_calls is True
            assert turn.tool_calls[0].name == "web.search"
