"""
Tests for ToolRegistry.

All tests use a fresh ToolRegistry instance per test (not the singleton)
to ensure full isolation.
"""
import pytest
from backend.tools.base import ToolSpec
from backend.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry()


async def _noop(args: dict) -> str:
    return "ok"


def make_spec(name: str = "web.search", risk: str = "read") -> ToolSpec:
    return ToolSpec(
        name=name,
        description="Test tool",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        risk=risk,
    )


# ── Registration ──────────────────────────────────────────────────────────────

def test_register_and_get_by_canonical(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search"), _noop)
    spec = registry.get("web.search")
    assert spec is not None
    assert spec.name == "web.search"


def test_get_by_alias(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search"), _noop)
    spec = registry.get("web__search")
    assert spec is not None
    assert spec.name == "web.search"


def test_duplicate_registration_raises(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search"), _noop)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(make_spec("web.search"), _noop)


def test_get_unknown_returns_none(registry: ToolRegistry) -> None:
    assert registry.get("does.not.exist") is None


def test_len(registry: ToolRegistry) -> None:
    assert len(registry) == 0
    registry.register(make_spec("web.search"), _noop)
    assert len(registry) == 1
    registry.register(make_spec("web.fetch"), _noop)
    assert len(registry) == 2


def test_contains(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search"), _noop)
    assert "web.search" in registry
    assert "web__search" in registry     # alias form
    assert "web.fetch" not in registry


# ── Alias roundtrip ───────────────────────────────────────────────────────────

def test_alias_roundtrip_simple(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search"), _noop)
    alias = registry.aliases.get_alias("web.search")
    assert alias == "web__search"
    assert registry.aliases.get_canonical(alias) == "web.search"


def test_alias_roundtrip_nested(registry: ToolRegistry) -> None:
    registry.register(make_spec("github.search_code"), _noop)
    alias = registry.aliases.get_alias("github.search_code")
    assert alias == "github__search_code"
    assert registry.aliases.get_canonical(alias) == "github.search_code"


# ── Filtering ─────────────────────────────────────────────────────────────────

def test_list_tools_enabled_only(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search"), _noop)
    disabled = ToolSpec(name="web.fetch", description="", input_schema={}, enabled=False)
    registry.register(disabled, _noop)

    enabled = registry.list_tools(enabled_only=True)
    names = [t.name for t in enabled]
    assert "web.search" in names
    assert "web.fetch" not in names

    all_tools = registry.list_tools(enabled_only=False)
    assert len(all_tools) == 2


def test_list_tools_max_risk_read(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search", risk="read"), _noop)
    registry.register(make_spec("code.execute", risk="privileged"), _noop)

    read_only = registry.list_tools(max_risk="read")
    names = [t.name for t in read_only]
    assert "web.search" in names
    assert "code.execute" not in names


def test_list_tools_max_risk_privileged_includes_all(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search", risk="read"), _noop)
    registry.register(make_spec("code.execute", risk="privileged"), _noop)

    all_tools = registry.list_tools(max_risk="privileged")
    names = [t.name for t in all_tools]
    assert "web.search" in names
    assert "code.execute" in names


# ── Provider spec export ──────────────────────────────────────────────────────

def test_get_specs_for_provider_uses_aliases(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search"), _noop)
    registry.register(make_spec("web.fetch"), _noop)

    specs = registry.get_specs_for_provider()
    names = [s["name"] for s in specs]
    assert "web__search" in names
    assert "web__fetch" in names
    assert "web.search" not in names   # canonical names must not appear here


def test_get_specs_for_provider_has_required_keys(registry: ToolRegistry) -> None:
    registry.register(make_spec("web.search"), _noop)
    specs = registry.get_specs_for_provider()
    assert len(specs) == 1
    assert "name" in specs[0]
    assert "description" in specs[0]
    assert "input_schema" in specs[0]
