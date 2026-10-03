"""Tests for Anthropic Claude Direct API Client.

All HTTP requests are mocked offline — 0 paid provider credits consumed.
"""

import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from backend.models.anthropic_client import AnthropicClient


class TestAnthropicClient:
    def test_missing_api_key_raises_error(self):
        client = AnthropicClient(api_key="")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            client._headers()

    def test_headers_structure(self):
        client = AnthropicClient(api_key="sk-ant-test-key")
        headers = client._headers()
        assert headers["x-api-key"] == "sk-ant-test-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert headers["Content-Type"] == "application/json"

    def test_format_messages_and_system(self):
        client = AnthropicClient(api_key="sk-ant-test")
        messages = [
            {"role": "system", "content": "You are a helpful coding assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "model", "content": "Hi there! How can I help?"},
            {"role": "user", "content": "Write a python script."},
        ]

        system, formatted = client._format_messages_and_system(
            messages=messages,
            system_prompt="Base prompt.",
            model_name="claude-sonnet-4-5"
        )

        assert "Base prompt." in system
        assert "You are a helpful coding assistant." in system
        assert len(formatted) == 3
        assert formatted[0]["role"] == "user"
        assert formatted[1]["role"] == "assistant"
        assert formatted[2]["role"] == "user"

    def test_format_messages_with_images_when_vision_supported(self):
        client = AnthropicClient(api_key="sk-ant-test")
        messages = [{"role": "user", "content": "What is in this image?"}]
        media_parts = [
            {"type": "image", "mime_type": "image/png", "bytes_b64": "iVBORw0KGgoAAAANSUhEUg=="}
        ]

        system, formatted = client._format_messages_and_system(
            messages=messages,
            media_parts=media_parts,
            model_name="claude-sonnet-4-5"
        )

        last_content = formatted[-1]["content"]
        assert isinstance(last_content, list)
        assert any(b.get("type") == "image" for b in last_content)
        assert any(b.get("type") == "text" and b.get("text") == "What is in this image?" for b in last_content)

    @pytest.mark.asyncio
    async def test_generate_success(self):
        client = AnthropicClient(api_key="sk-ant-test")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "id": "msg_01",
            "content": [
                {"type": "text", "text": "Hello from Claude!"}
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client.generate(
                messages=[{"role": "user", "content": "Say hello"}],
                model_name="claude-sonnet-4-5",
                temperature=0.5
            )

            assert result == "Hello from Claude!"
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args[1]
            assert call_kwargs["json"]["model"] == "claude-sonnet-4-5"
            assert call_kwargs["json"]["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_generate_thinking_mode(self):
        client = AnthropicClient(api_key="sk-ant-test")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "content": [{"type": "text", "text": "Solved with thinking!"}]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client.generate(
                messages=[{"role": "user", "content": "Complex math problem"}],
                model_name="claude-3-7-sonnet-latest",
                thinking_enabled=True
            )

            assert result == "Solved with thinking!"
            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs["json"]
            assert "thinking" in payload
            assert payload["thinking"]["type"] == "enabled"
            assert payload["thinking"]["budget_tokens"] == 2048
            assert payload["temperature"] == 1.0

    @pytest.mark.asyncio
    async def test_generate_http_error_raises_runtime_error(self):
        client = AnthropicClient(api_key="sk-ant-test")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 401
        mock_response.text = "Invalid API Key"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(RuntimeError, match="Anthropic API Error \\(401\\)"):
                await client.generate(messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_generate_stream_success(self):
        client = AnthropicClient(api_key="sk-ant-test")

        sse_lines = [
            "event: message_start\n",
            'data: {"type": "message_start"}\n',
            "event: content_block_delta\n",
            'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Claude "}}\n',
            "event: content_block_delta\n",
            'data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Streaming!"}}\n',
            "event: message_stop\n",
            'data: {"type": "message_stop"}\n',
        ]

        class MockStreamResponse:
            status_code = 200

            async def aiter_lines(self):
                for line in sse_lines:
                    yield line

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        with patch("httpx.AsyncClient.stream", return_value=MockStreamResponse()):
            chunks = []
            async for chunk in client.generate_stream(
                messages=[{"role": "user", "content": "Hi"}]
            ):
                chunks.append(chunk)

            assert "".join(chunks) == "Claude Streaming!"
