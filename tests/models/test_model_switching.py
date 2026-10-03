"""Tests for Model Router Dispatching, Tier Enforcement, and Model Switching API."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.models.router import model_router
from backend.config import settings


class TestModelRouterDispatching:
    @pytest.mark.asyncio
    async def test_dispatch_to_anthropic(self):
        with patch.object(model_router.anthropic_client, "generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Claude response"
            res = await model_router.generate(
                messages=[{"role": "user", "content": "hi"}],
                provider="anthropic",
                model_name="claude-sonnet-4-5"
            )
            assert res == "Claude response"
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_to_qwen(self):
        with patch.object(model_router.qwen_client, "generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Qwen response"
            res = await model_router.generate(
                messages=[{"role": "user", "content": "hi"}],
                provider="qwen",
                model_name="qwen-turbo"
            )
            assert res == "Qwen response"
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_to_deepseek(self):
        with patch.object(model_router.deepseek_client, "generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "DeepSeek response"
            res = await model_router.generate(
                messages=[{"role": "user", "content": "hi"}],
                provider="deepseek",
                model_name="deepseek-chat"
            )
            assert res == "DeepSeek response"
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_to_gemini(self):
        with patch.object(model_router.gemini_client, "generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Gemini response"
            res = await model_router.generate(
                messages=[{"role": "user", "content": "hi"}],
                provider="gemini",
                model_name="gemini-2.5-flash"
            )
            assert res == "Gemini response"
            mock_gen.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_provider_raises_error(self):
        with pytest.raises(ValueError, match="Unknown model provider"):
            await model_router.generate(
                messages=[{"role": "user", "content": "hi"}],
                provider="completely_fictional_provider"
            )

    @pytest.mark.asyncio
    async def test_vision_fallback_for_non_vision_model(self):
        # DigitalOcean does not support vision natively, so vision fallback should be called
        with patch.object(model_router, "_handle_vision_fallback", new_callable=AsyncMock) as mock_vision:
            with patch.object(model_router.do_client, "generate", new_callable=AsyncMock) as mock_gen:
                mock_gen.return_value = "DO response"
                media_parts = [{"type": "image", "bytes_b64": "abc", "mime_type": "image/png"}]
                await model_router.generate(
                    messages=[{"role": "user", "content": "look at this"}],
                    provider="digitalocean",
                    media_parts=media_parts
                )
                mock_vision.assert_called_once()


class TestModelSwitchingAPI:
    @property
    def auth_headers(self):
        token = settings.INTERNAL_API_KEY or "test_key"
        return {"X-Zauq-Token": token}

    @pytest.fixture(autouse=True)
    def setup_internal_key(self, monkeypatch):
        monkeypatch.setattr(settings, "INTERNAL_API_KEY", "test_internal_key")

    @pytest.mark.asyncio
    async def test_tier_mismatch_rejected(self):
        transport = ASGITransport(app=app)
        headers = {"X-Zauq-Token": "test_internal_key"}
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Tier 2 + Anthropic should be rejected with 400
            res = await ac.post("/api/model/set", headers=headers, json={
                "channel_id": "chan_123",
                "tier": 2,
                "provider": "anthropic",
                "model_name": "claude-sonnet-4-5"
            })
            assert res.status_code == 400
            assert "Invalid provider" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_missing_credentials_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
        transport = ASGITransport(app=app)
        headers = {"X-Zauq-Token": "test_internal_key"}
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post("/api/model/set", headers=headers, json={
                "channel_id": "chan_123",
                "tier": 1,
                "provider": "anthropic",
                "model_name": "claude-sonnet-4-5"
            })
            assert res.status_code == 400
            assert "Credential validation failed" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_valid_anthropic_switch_succeeds(self, monkeypatch):
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test-key")
        transport = ASGITransport(app=app)
        headers = {"X-Zauq-Token": "test_internal_key"}
        mock_saved = {
            "channel_id": "chan_123",
            "tier": 1,
            "provider": "anthropic",
            "model_name": "claude-sonnet-4-5",
            "updated_by": "Admin"
        }
        with patch("backend.routers.model.db_helper.upsert_model_selection", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = mock_saved
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                res = await ac.post("/api/model/set", headers=headers, json={
                    "channel_id": "chan_123",
                    "tier": 1,
                    "provider": "anthropic",
                    "model_name": "claude-sonnet-4-5",
                    "scope": "channel"
                })
                assert res.status_code == 200
                data = res.json()
                assert data["status"] == "success"
                assert data["scope"] == "channel"
                assert data["data"]["provider"] == "anthropic"

    @pytest.mark.asyncio
    async def test_valid_qwen_switch_succeeds(self, monkeypatch):
        monkeypatch.setattr(settings, "QWEN_API_KEY", "sk-qwen-key")
        monkeypatch.setattr(settings, "QWEN_BASE_URL", "https://dashscope.aliyuncs.com")
        transport = ASGITransport(app=app)
        headers = {"X-Zauq-Token": "test_internal_key"}
        mock_saved = {
            "channel_id": "chan_456",
            "tier": 1,
            "provider": "qwen",
            "model_name": "qwen-turbo",
            "updated_by": "Admin"
        }
        with patch("backend.routers.model.db_helper.upsert_model_selection", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = mock_saved
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                res = await ac.post("/api/model/set", headers=headers, json={
                    "channel_id": "chan_456",
                    "tier": 1,
                    "provider": "qwen",
                    "model_name": "qwen-turbo",
                    "scope": "channel"
                })
                assert res.status_code == 200
                data = res.json()
                assert data["data"]["provider"] == "qwen"

    @pytest.mark.asyncio
    async def test_valid_deepseek_switch_succeeds(self, monkeypatch):
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "sk-deepseek-key")
        transport = ASGITransport(app=app)
        headers = {"X-Zauq-Token": "test_internal_key"}
        mock_saved = {
            "channel_id": "chan_789",
            "tier": 1,
            "provider": "deepseek",
            "model_name": "deepseek-chat",
            "updated_by": "Admin"
        }
        with patch("backend.routers.model.db_helper.upsert_model_selection", new_callable=AsyncMock) as mock_db:
            mock_db.return_value = mock_saved
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                res = await ac.post("/api/model/set", headers=headers, json={
                    "channel_id": "chan_789",
                    "tier": 1,
                    "provider": "deepseek",
                    "model_name": "deepseek-chat",
                    "scope": "channel"
                })
                assert res.status_code == 200
                data = res.json()
                assert data["data"]["provider"] == "deepseek"

    @pytest.mark.asyncio
    async def test_providers_endpoint(self):
        transport = ASGITransport(app=app)
        headers = {"X-Zauq-Token": "test_internal_key"}
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get("/api/model/providers", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert "providers" in data
            provider_ids = [p["id"] for p in data["providers"]]
            assert "anthropic" in provider_ids
            assert "qwen" in provider_ids
            assert "deepseek" in provider_ids

    @pytest.mark.asyncio
    async def test_catalog_endpoint(self):
        transport = ASGITransport(app=app)
        headers = {"X-Zauq-Token": "test_internal_key"}
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get("/api/model/catalog/anthropic", headers=headers)
            assert res.status_code == 200
            data = res.json()
            assert data["provider"] == "anthropic"
            assert "claude-sonnet-4-5" in data["models"]

