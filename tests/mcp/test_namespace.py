"""Tests for MCP canonical namespacing, aliases, and ambiguity prevention."""

import pytest
from backend.mcp_client.adapter import make_canonical_name
from backend.tools.aliases import AliasMap, canonical_to_alias, alias_to_canonical


def test_make_canonical_name_default():
    name = make_canonical_name("github", "search_issues")
    assert name == "mcp.github.search_issues"


def test_make_canonical_name_custom_prefix():
    name = make_canonical_name("github", "search_issues", namespace_prefix="github")
    assert name == "github.search_issues"

    name2 = make_canonical_name("local-docs", "find_document", namespace_prefix="docs")
    assert name2 == "docs.find_document"


def test_make_canonical_name_requires_namespace():
    # Attempting to produce a bare unnamespaced name should fail
    with pytest.raises(ValueError, match="at least one namespace prefix"):
        make_canonical_name("", "search", namespace_prefix="")


def test_alias_map_integration():
    alias_map = AliasMap()

    canonical_1 = "mcp.github.search_code"
    alias_1 = alias_map.register(canonical_1)
    assert alias_1 == "mcp__github__search_code"
    assert alias_map.resolve(alias_1) == canonical_1
    assert alias_map.resolve(canonical_1) == canonical_1

    # Unregister
    alias_map.unregister(canonical_1)
    with pytest.raises(KeyError):
        alias_map.resolve(canonical_1)
    with pytest.raises(KeyError):
        alias_map.resolve(alias_1)


def test_alias_bidirectional_helpers():
    assert canonical_to_alias("mcp.github.get_pr") == "mcp__github__get_pr"
    assert alias_to_canonical("mcp__github__get_pr") == "mcp.github.get_pr"
