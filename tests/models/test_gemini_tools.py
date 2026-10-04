"""Tests for Gemini Native Function Calling and Tool Normalization."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from backend.models.gemini_client import GeminiClient
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


class TestGeminiTools:
    @pytest.mark.asyncio
    async def test_gemini_returns_tool_call(self, sample_tool):
        client = GeminiClient(api_key="mock_gemini_key")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "web__search",
                                    "args": {"query": "latest AI news"}
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
                messages=[{"role": "user", "content": "What is the latest AI news?"}],
                tools=[sample_tool],
                model_name="gemini-2.5-flash"
            )

            assert isinstance(turn, AgentModelTurn)
            assert turn.has_tool_calls is True
            assert len(turn.tool_calls) == 1

            call = turn.tool_calls[0]
            assert call.name == "web.search"  # Normalized from web__search
            assert call.arguments == {"query": "latest AI news"}

    @pytest.mark.asyncio
    async def test_gemini_returns_final_text(self, sample_tool):
        client = GeminiClient(api_key="mock_gemini_key")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "The latest AI news includes Gemini 2.5."}
                        ]
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            turn = await client.generate_agent_turn(
                messages=[{"role": "user", "content": "Tell me news"}],
                tools=[sample_tool]
            )

            assert isinstance(turn, AgentModelTurn)
            assert turn.has_tool_calls is False
            assert turn.is_final_answer is True
            assert "Gemini 2.5" in turn.text

    @pytest.mark.asyncio
    async def test_gemini_serializes_tool_result_message(self, sample_tool):
        client = GeminiClient(api_key="mock_gemini_key")
        messages = [
            {"role": "user", "content": "Search for cats"},
            {
                "role": "model",
                "tool_calls": [ToolCall(id="call_1", name="web.search", arguments={"query": "cats"})]
            },
            ToolResultMessage(
                tool_call_id="call_1",
                tool_name="web.search",
                content="Cats are popular domestic pets.",
                is_error=False
            )
        ]

        payload = client._prepare_payload(messages=messages, tools=[sample_tool])
        contents = payload["contents"]

        assert len(contents) == 3
        # First turn: user text
        assert contents[0]["role"] == "user"
        # Second turn: model function call
        assert contents[1]["role"] == "model"
        assert "functionCall" in contents[1]["parts"][0]
        assert contents[1]["parts"][0]["functionCall"]["name"] == "web__search"
        # Third turn: function response
        assert contents[2]["role"] == "user"
        assert "functionResponse" in contents[2]["parts"][0]
        assert contents[2]["parts"][0]["functionResponse"]["name"] == "web__search"
        assert contents[2]["parts"][0]["functionResponse"]["response"]["content"] == "Cats are popular domestic pets."
