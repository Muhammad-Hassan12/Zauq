"""Tests for Provider Tier Rules and Credential Validation."""

import pytest
from backend.models.catalog import (
    validate_provider_tier,
    validate_provider_credentials,
    VALID_TIER_PROVIDERS,
)
from backend.config import settings


class TestProviderTierValidation:
    def test_tier_1_valid_providers(self):
        tier_1_providers = ["gemini", "digitalocean", "anthropic", "qwen", "deepseek"]
        for p in tier_1_providers:
            assert validate_provider_tier(p, 1) is True, f"{p} should be valid for Tier 1"

    def test_tier_1_invalid_providers(self):
        invalid = ["ollama", "kaggle", "unknown_provider"]
        for p in invalid:
            assert validate_provider_tier(p, 1) is False, f"{p} should not be valid for Tier 1"

    def test_tier_2_valid_providers(self):
        assert validate_provider_tier("ollama", 2) is True
        assert validate_provider_tier("local", 2) is True  # alias normalization

    def test_tier_2_invalid_providers(self):
        # Tier 2 + Anthropic must fail cleanly
        assert validate_provider_tier("anthropic", 2) is False
        assert validate_provider_tier("gemini", 2) is False
        assert validate_provider_tier("qwen", 2) is False
        assert validate_provider_tier("deepseek", 2) is False
        assert validate_provider_tier("kaggle", 2) is False

    def test_tier_3_valid_providers(self):
        assert validate_provider_tier("kaggle", 3) is True
        assert validate_provider_tier("batch gpu", 3) is True

    def test_tier_3_invalid_providers(self):
        assert validate_provider_tier("anthropic", 3) is False
        assert validate_provider_tier("gemini", 3) is False
        assert validate_provider_tier("digitalocean", 3) is False
        assert validate_provider_tier("ollama", 3) is False

    def test_invalid_tier_number(self):
        assert validate_provider_tier("anthropic", 0) is False
        assert validate_provider_tier("anthropic", 4) is False


class TestProviderCredentialValidation:
    def test_anthropic_credential_validation(self, monkeypatch):
        # When missing key
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
        valid, err = validate_provider_credentials("anthropic")
        assert valid is False
        assert "ANTHROPIC_API_KEY" in err

        # When key configured
        monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-api03-mockkey")
        valid, err = validate_provider_credentials("anthropic")
        assert valid is True
        assert err is None

    def test_qwen_credential_validation(self, monkeypatch):
        # Missing key
        monkeypatch.setattr(settings, "QWEN_API_KEY", "")
        monkeypatch.setattr(settings, "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        valid, err = validate_provider_credentials("qwen")
        assert valid is False
        assert "QWEN_API_KEY" in err

        # Missing base URL
        monkeypatch.setattr(settings, "QWEN_API_KEY", "sk-qwen-mock")
        monkeypatch.setattr(settings, "QWEN_BASE_URL", "")
        valid, err = validate_provider_credentials("qwen")
        assert valid is False
        assert "QWEN_BASE_URL" in err

        # Both present
        monkeypatch.setattr(settings, "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        valid, err = validate_provider_credentials("qwen")
        assert valid is True
        assert err is None

    def test_deepseek_credential_validation(self, monkeypatch):
        # Missing key
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "")
        valid, err = validate_provider_credentials("deepseek")
        assert valid is False
        assert "DEEPSEEK_API_KEY" in err

        # Key present
        monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "sk-deepseek-mock")
        valid, err = validate_provider_credentials("deepseek")
        assert valid is True
        assert err is None

    def test_unknown_provider_credential_validation(self):
        valid, err = validate_provider_credentials("some_fake_provider")
        assert valid is False
        assert "Unknown provider" in err
