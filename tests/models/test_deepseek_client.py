"""Tests for DeepSeek Direct API Client.

All requests are mocked offline — 0 paid provider credits consumed.
"""

import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from backend.models.deepseek_client import DeepSeekClient


class TestDeepSeekClient:
    def test_missing_api_key_raises_error(self):
        client = DeepSeekClient(api_key="")
        with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
            client._headers()

    def test_headers_structure(self):
        client = DeepSeekClient(api_key="sk-deepseek-test")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer sk-deepseek-test"
        assert headers["Content-Type"] == "application/json"

    def test_build_payload_standard(self):
        client = DeepSeekClient(api_key="sk-deepseek-test")
        model, payload = client._build_payload(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be concise.",
            temperature=0.7,
            model_name="deepseek-chat",
            thinking_enabled=False
        )
        assert model == "deepseek-chat"
        assert payload["model"] == "deepseek-chat"
        assert payload["temperature"] == 0.7
        assert len(payload["messages"]) == 2

    def test_build_payload_thinking_mode_upgrades_to_reasoner(self):
        client = DeepSeekClient(api_key="sk-deepseek-test")
        model, payload = client._build_payload(
            messages=[{"role": "user", "content": "Solve math proof"}],
            model_name="deepseek-chat",
            thinking_enabled=True
        )
        # Upgrades to deepseek-reasoner and omits temperature
        assert model == "deepseek-reasoner"
        assert payload["model"] == "deepseek-reasoner"
        assert "temperature" not in payload

    @pytest.mark.asyncio
    async def test_generate_success(self):
        client = DeepSeekClient(api_key="sk-deepseek-test")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "DeepSeek response content",
                        "reasoning_content": "Deep systematic reasoning..."
                    }
                }
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client.generate(
                messages=[{"role": "user", "content": "Hello"}],
                model_name="deepseek-chat"
            )

            assert result == "DeepSeek response content"
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_http_error(self):
        client = DeepSeekClient(api_key="sk-deepseek-test")
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(RuntimeError, match="DeepSeek API Error \\(429\\)"):
                await client.generate(messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_generate_stream_success(self):
        client = DeepSeekClient(api_key="sk-deepseek-test")

        sse_lines = [
            'data: {"choices": [{"delta": {"content": "DeepSeek "}}]}\n',
            'data: {"choices": [{"delta": {"content": "stream."}}]}\n',
            'data: [DONE]\n'
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

            assert "".join(chunks) == "DeepSeek stream."
