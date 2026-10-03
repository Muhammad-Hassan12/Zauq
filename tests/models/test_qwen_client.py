"""Tests for Alibaba Cloud Model Studio / Qwen Direct API Client.

All requests are mocked offline — 0 paid provider credits consumed.
"""

import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from backend.models.qwen_client import QwenClient


class TestQwenClient:
    def test_missing_credentials_raises_error(self):
        client_no_key = QwenClient(api_key="", base_url="https://dashscope.aliyuncs.com")
        with pytest.raises(ValueError, match="QWEN_API_KEY"):
            client_no_key._headers()

    @pytest.mark.asyncio
    async def test_missing_base_url_raises_error(self):
        client = QwenClient(api_key="sk-qwen-key", base_url="")
        with pytest.raises(ValueError, match="QWEN_BASE_URL"):
            await client.generate(messages=[{"role": "user", "content": "Hi"}])

    def test_headers_structure(self):
        client = QwenClient(api_key="sk-qwen-test-key", base_url="https://dashscope.aliyuncs.com")
        headers = client._headers()
        assert headers["Authorization"] == "Bearer sk-qwen-test-key"
        assert headers["Content-Type"] == "application/json"

    def test_build_payload(self):
        client = QwenClient(api_key="sk-qwen", base_url="https://dashscope.aliyuncs.com")
        model, payload = client._build_payload(
            messages=[{"role": "user", "content": "Hello"}],
            system_prompt="Be concise.",
            temperature=0.7,
            model_name="qwen-plus"
        )
        assert model == "qwen-plus"
        assert payload["model"] == "qwen-plus"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"

    @pytest.mark.asyncio
    async def test_generate_success(self):
        client = QwenClient(
            api_key="sk-qwen-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {"message": {"role": "assistant", "content": "Hello from Qwen!"}}
            ]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await client.generate(
                messages=[{"role": "user", "content": "Hi"}],
                model_name="qwen-turbo"
            )

            assert result == "Hello from Qwen!"
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_http_error(self):
        client = QwenClient(
            api_key="sk-qwen-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            with pytest.raises(RuntimeError, match="Qwen API Error \\(403\\)"):
                await client.generate(messages=[{"role": "user", "content": "Hi"}])

    @pytest.mark.asyncio
    async def test_generate_stream_success(self):
        client = QwenClient(
            api_key="sk-qwen-key",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        sse_lines = [
            'data: {"choices": [{"delta": {"content": "Qwen "}}]}\n',
            'data: {"choices": [{"delta": {"content": "streaming!"}}]}\n',
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

            assert "".join(chunks) == "Qwen streaming!"
