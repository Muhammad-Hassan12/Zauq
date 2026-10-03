"""Tests for the Centralized Provider and Model Catalog."""

import pytest
from backend.models.catalog import (
    PROVIDERS,
    VALID_TIER_PROVIDERS,
    normalize_provider_id,
    get_provider,
    list_providers,
    get_models_for_provider,
    validate_provider_tier,
)


class TestProviderCatalog:
    def test_all_seven_providers_registered(self):
        expected_providers = {
            "gemini",
            "digitalocean",
            "anthropic",
            "qwen",
            "deepseek",
            "ollama",
            "kaggle",
        }
        assert set(PROVIDERS.keys()) == expected_providers

    def test_provider_normalization(self):
        # Gemini variants
        assert normalize_provider_id("google") == "gemini"
        assert normalize_provider_id("Gemini") == "gemini"
        assert normalize_provider_id("Google AI Studio") == "gemini"
        assert normalize_provider_id("gemma") == "gemini"

        # DigitalOcean variants
        assert normalize_provider_id("do") == "digitalocean"
        assert normalize_provider_id("DigitalOcean") == "digitalocean"
        assert normalize_provider_id("gradient") == "digitalocean"

        # Anthropic variants
        assert normalize_provider_id("anthropic") == "anthropic"
        assert normalize_provider_id("Claude") == "anthropic"

        # Qwen variants
        assert normalize_provider_id("qwen") == "qwen"
        assert normalize_provider_id("Alibaba") == "qwen"
        assert normalize_provider_id("alibaba qwen") == "qwen"
        assert normalize_provider_id("dashscope") == "qwen"

        # DeepSeek variants
        assert normalize_provider_id("deepseek") == "deepseek"
        assert normalize_provider_id("Deep Seek") == "deepseek"

        # Ollama variants
        assert normalize_provider_id("ollama") == "ollama"
        assert normalize_provider_id("Local") == "ollama"
        assert normalize_provider_id("vps") == "ollama"

        # Kaggle variants
        assert normalize_provider_id("kaggle") == "kaggle"
        assert normalize_provider_id("Batch GPU") == "kaggle"
        assert normalize_provider_id("kaggle t4") == "kaggle"

    def test_get_provider_spec(self):
        spec = get_provider("claude")
        assert spec is not None
        assert spec.id == "anthropic"
        assert spec.tier == 1
        assert "claude-sonnet-4-5" in spec.models or "claude-3-7-sonnet-latest" in spec.models

        spec_qwen = get_provider("alibaba")
        assert spec_qwen is not None
        assert spec_qwen.id == "qwen"
        assert spec_qwen.tier == 1

        spec_deepseek = get_provider("deepseek")
        assert spec_deepseek is not None
        assert spec_deepseek.id == "deepseek"
        assert spec_deepseek.tier == 1

    def test_get_models_for_provider(self):
        models = get_models_for_provider("anthropic")
        assert len(models) >= 3
        assert any("claude" in m for m in models)

        qwen_models = get_models_for_provider("qwen")
        assert len(qwen_models) >= 3
        assert any("qwen" in m for m in qwen_models)

        deepseek_models = get_models_for_provider("deepseek")
        assert len(deepseek_models) >= 2
        assert "deepseek-chat" in deepseek_models

    def test_list_providers_returns_all(self):
        providers = list_providers()
        assert len(providers) == 7
        ids = [p.id for p in providers]
        assert "anthropic" in ids
        assert "qwen" in ids
        assert "deepseek" in ids
