"""
Tests for ToolExecutor.

Uses isolated ToolRegistry and ToolPolicy instances per test.
No real tools, network calls, or LLM interaction.
"""
import asyncio
import pytest
from backend.tools.base import ToolSpec
from backend.tools.registry import ToolRegistry
from backend.tools.executor import ToolExecutor
from backend.tools.policy import ToolPolicy


@pytest.fixture
def rig() -> tuple[ToolRegistry, ToolExecutor]:
    """Fresh registry + executor pair per test."""
    reg = ToolRegistry()
    policy = ToolPolicy()
    executor = ToolExecutor(reg, policy)
    return reg, executor


def make_spec(
    name: str,
    risk: str = "read",
    timeout: float = 5.0,
    enabled: bool = True,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description="",
        input_schema={},
        risk=risk,
        timeout_seconds=timeout,
        enabled=enabled,
    )


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_successful_execution(rig: tuple) -> None:
    reg, executor = rig

    async def handler(args: dict) -> str:
        return f"result:{args.get('q')}"

    reg.register(make_spec("test.tool"), handler)
    result = await executor.execute("test.tool", {"q": "hello"})

    assert result.success is True
    assert result.content == "result:hello"
    assert result.error is None
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_execution_by_alias(rig: tuple) -> None:
    """Executor should accept the provider-safe alias, not just canonical."""
    reg, executor = rig

    async def handler(args: dict) -> str:
        return "alias_ok"

    reg.register(make_spec("web.search"), handler)
    result = await executor.execute("web__search", {})  # alias form

    assert result.success is True
    assert result.tool_name == "web.search"  # canonical name in result


@pytest.mark.asyncio
async def test_result_contains_tool_name(rig: tuple) -> None:
    reg, executor = rig

    async def handler(args: dict) -> str:
        return "x"

    reg.register(make_spec("my.tool"), handler)
    result = await executor.execute("my.tool", {})
    assert result.tool_name == "my.tool"


# ── Unknown tool ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_tool_returns_failure(rig: tuple) -> None:
    _, executor = rig
    result = await executor.execute("nonexistent.tool", {})

    assert result.success is False
    assert "Unknown tool" in result.error
    assert result.duration_ms == 0


# ── Timeout ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_enforced(rig: tuple) -> None:
    reg, executor = rig

    async def slow(args: dict) -> str:
        await asyncio.sleep(10)
        return "never reached"

    reg.register(make_spec("slow.tool", timeout=0.05), slow)
    result = await executor.execute("slow.tool", {})

    assert result.success is False
    assert "timed out" in result.error.lower()


@pytest.mark.asyncio
async def test_timeout_result_has_duration(rig: tuple) -> None:
    reg, executor = rig

    async def slow(args: dict) -> str:
        await asyncio.sleep(10)
        return "never"

    reg.register(make_spec("slow2.tool", timeout=0.05), slow)
    result = await executor.execute("slow2.tool", {})
    assert result.duration_ms >= 0


# ── Policy blocking ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_write_risk_is_denied(rig: tuple) -> None:
    reg, executor = rig

    async def handler(args: dict) -> str:
        return "should not run"

    reg.register(make_spec("write.tool", risk="write"), handler)
    result = await executor.execute("write.tool", {})

    assert result.success is False
    assert "denied by policy" in result.error


@pytest.mark.asyncio
async def test_destructive_risk_is_denied(rig: tuple) -> None:
    reg, executor = rig

    async def handler(args: dict) -> str:
        return "boom"

    reg.register(make_spec("destroy.everything", risk="destructive"), handler)
    result = await executor.execute("destroy.everything", {})

    assert result.success is False
    assert "denied by policy" in result.error


@pytest.mark.asyncio
async def test_privileged_without_allowlist_is_denied(rig: tuple) -> None:
    reg, executor = rig

    async def handler(args: dict) -> str:
        return "privileged result"

    reg.register(make_spec("code.execute", risk="privileged"), handler)
    # Default ToolPolicy has empty allowlist in rig fixture
    result = await executor.execute("code.execute", {})

    assert result.success is False
    assert "denied by policy" in result.error


# ── Exception from handler ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handler_exception_is_captured(rig: tuple) -> None:
    reg, executor = rig

    async def broken(args: dict) -> str:
        raise RuntimeError("something broke inside the tool")

    reg.register(make_spec("broken.tool"), broken)
    result = await executor.execute("broken.tool", {})

    assert result.success is False
    assert "something broke inside the tool" in result.error


# ── Disabled tool ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_disabled_tool_is_denied(rig: tuple) -> None:
    reg, executor = rig

    async def handler(args: dict) -> str:
        return "should not run"

    reg.register(make_spec("off.tool", enabled=False), handler)
    result = await executor.execute("off.tool", {})

    assert result.success is False
