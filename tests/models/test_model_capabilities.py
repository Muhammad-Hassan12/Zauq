"""Tests for Provider/Model Tool Capabilities and Router Enforcement."""

import pytest
from unittest.mock import AsyncMock, patch
from backend.models.capabilities import supports_native_tools
from backend.models.router import model_router
from backend.tools.base import ToolSpec
from backend.agent.types import AgentModelTurn, ToolCall


@pytest.fixture
def sample_tool():
    return ToolSpec(
        name="web.search",
        description="Search the web",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}}
    )


class TestModelCapabilities:
    def test_gemini_native_tools_support(self):
        assert supports_native_tools("gemini", "gemini-2.5-flash") is True
        assert supports_native_tools("gemini", "gemini-2.5-pro") is True
        assert supports_native_tools("gemini", "gemini-3.6-flash") is True
        # Gemma open models are text-only
        assert supports_native_tools("gemini", "gemma-4-26b-a4b-it") is False

    def test_anthropic_native_tools_support(self):
        assert supports_native_tools("anthropic", "claude-sonnet-4-5") is True
        assert supports_native_tools("anthropic", "claude-3-7-sonnet-latest") is True
        assert supports_native_tools("anthropic", "claude-3-5-sonnet-latest") is True

    def test_qwen_native_tools_support(self):
        assert supports_native_tools("qwen", "qwen-turbo") is True
        assert supports_native_tools("qwen", "qwen-plus") is True
        assert supports_native_tools("qwen", "qwen-max") is True
        assert supports_native_tools("qwen", "qwen2.5-72b-instruct") is True

    def test_deepseek_native_tools_support(self):
        # DeepSeek-V3 supports tools
        assert supports_native_tools("deepseek", "deepseek-chat") is True
        # DeepSeek-Reasoner (R1) does not support function calling
        assert supports_native_tools("deepseek", "deepseek-reasoner") is False

    def test_digitalocean_allowlist(self):
        # Allowlisted model
        assert supports_native_tools("digitalocean", "llama3.3-70b-instruct") is True
        # Non-allowlisted models
        assert supports_native_tools("digitalocean", "kimi-k3") is False
        assert supports_native_tools("digitalocean", "glm-5.1") is False

    def test_ollama_and_kaggle_disabled_by_default(self):
        assert supports_native_tools("ollama", "qwen3.5:4b") is False
        assert supports_native_tools("kaggle", "qwen3.5-t4") is False


class TestRouterToolEnforcement:
    @pytest.mark.asyncio
    async def test_router_rejects_tools_for_unsupported_provider(self, sample_tool):
        # Passing tools to Ollama should raise ValueError
        with pytest.raises(ValueError, match="does not support native tool calling"):
            await model_router.generate_agent_turn(
                messages=[{"role": "user", "content": "Search"}],
                tools=[sample_tool],
                provider="ollama"
            )

        # Passing tools to Kaggle should raise ValueError
        with pytest.raises(ValueError, match="does not support native tool calling"):
            await model_router.generate_agent_turn(
                messages=[{"role": "user", "content": "Search"}],
                tools=[sample_tool],
                provider="kaggle"
            )

    @pytest.mark.asyncio
    async def test_router_dispatches_agent_turn_to_gemini(self, sample_tool):
        expected_turn = AgentModelTurn(
            text=None,
            tool_calls=[ToolCall(id="c1", name="web.search", arguments={"query": "test"})]
        )
        with patch.object(model_router.gemini_client, "generate_agent_turn", new_callable=AsyncMock) as mock_agent:
            mock_agent.return_value = expected_turn
            turn = await model_router.generate_agent_turn(
                messages=[{"role": "user", "content": "Search"}],
                tools=[sample_tool],
                provider="gemini",
                model_name="gemini-2.5-flash"
            )
            assert turn == expected_turn
            mock_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_router_dispatches_agent_turn_to_anthropic(self, sample_tool):
        expected_turn = AgentModelTurn(
            text="Looking up info",
            tool_calls=[ToolCall(id="c2", name="web.search", arguments={"query": "test"})]
        )
        with patch.object(model_router.anthropic_client, "generate_agent_turn", new_callable=AsyncMock) as mock_agent:
            mock_agent.return_value = expected_turn
            turn = await model_router.generate_agent_turn(
                messages=[{"role": "user", "content": "Search"}],
                tools=[sample_tool],
                provider="anthropic",
                model_name="claude-sonnet-4-5"
            )
            assert turn == expected_turn
            mock_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_router_non_tool_generate_still_works(self):
        # Non-tool generate() remains completely functional
        with patch.object(model_router.gemini_client, "generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Normal response text"
            res = await model_router.generate(
                messages=[{"role": "user", "content": "hello"}],
                provider="gemini"
            )
            assert res == "Normal response text"
            mock_gen.assert_called_once()
