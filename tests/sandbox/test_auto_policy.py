"""Tests for auto_code_test_mode policy decisions in Zauq v4.

Verifies:
- off: code.execute is NEVER selected, even with code intent.
- auto: code.execute is selected only when code intent is detected.
- always: code.execute is selected whenever allow_code_exec=True.
- allow_code_exec=False: code.execute is NEVER selected regardless of auto mode.
"""

import pytest
from backend.agent.capability_router import CapabilityRouter
from backend.tools.base import ToolSpec
from backend.tools.registry import ToolRegistry


@pytest.fixture
def mock_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="code.execute",
            description="Run code in sandbox",
            input_schema={"type": "object", "properties": {"code": {"type": "string"}}},
            risk="privileged",
        ),
        lambda args: {"stdout": "ok"},
    )
    return reg


@pytest.fixture
def router(mock_registry: ToolRegistry) -> CapabilityRouter:
    return CapabilityRouter(registry=mock_registry)


def test_auto_policy_off_blocks_code_execute(router: CapabilityRouter):
    """When auto_code_test_mode is 'off', code.execute is not selected."""
    tools = router.select_tools(
        messages=[{"role": "user", "content": "execute python code: print('hello')"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        allow_code_exec=True,
        auto_code_test_mode="off",
    )
    assert "code.execute" not in [t.name for t in tools]


def test_auto_policy_auto_selects_on_intent(router: CapabilityRouter):
    """When auto_code_test_mode is 'auto', code.execute is selected only if code intent is present."""
    # With code intent
    tools_with_intent = router.select_tools(
        messages=[{"role": "user", "content": "run python: print(1+1)"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        allow_code_exec=True,
        auto_code_test_mode="auto",
    )
    assert "code.execute" in [t.name for t in tools_with_intent]

    # Without code intent
    tools_without_intent = router.select_tools(
        messages=[{"role": "user", "content": "What is the capital of France?"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        allow_code_exec=True,
        auto_code_test_mode="auto",
    )
    assert "code.execute" not in [t.name for t in tools_without_intent]


def test_auto_policy_always_selects_unconditionally(router: CapabilityRouter):
    """When auto_code_test_mode is 'always', code.execute is selected if allow_code_exec=True."""
    tools = router.select_tools(
        messages=[{"role": "user", "content": "Write a quick sorting function"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        allow_code_exec=True,
        auto_code_test_mode="always",
    )
    assert "code.execute" in [t.name for t in tools]


def test_allow_code_exec_false_always_blocks(router: CapabilityRouter):
    """If allow_code_exec is False, code.execute is blocked even under 'always'."""
    tools = router.select_tools(
        messages=[{"role": "user", "content": "execute python script"}],
        provider="gemini",
        model_name="gemini-2.5-flash",
        allow_code_exec=False,
        auto_code_test_mode="always",
    )
    assert "code.execute" not in [t.name for t in tools]
