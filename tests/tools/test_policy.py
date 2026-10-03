"""
Tests for ToolPolicy.

Verifies that policy decisions are correct for all risk levels and
that the LLM never has a path to bypass policy.
"""
from backend.tools.base import ToolSpec
from backend.tools.policy import ToolPolicy, PolicyDecision


def make_spec(
    risk: str = "read",
    name: str = "web.search",
    enabled: bool = True,
) -> ToolSpec:
    return ToolSpec(name=name, description="", input_schema={}, risk=risk, enabled=enabled)


# ── Enabled check ─────────────────────────────────────────────────────────────

def test_disabled_tool_is_denied() -> None:
    policy = ToolPolicy()
    assert policy.evaluate(make_spec(risk="read", enabled=False)) == PolicyDecision.DENY


# ── Risk: read ────────────────────────────────────────────────────────────────

def test_read_risk_is_allowed() -> None:
    policy = ToolPolicy()
    assert policy.evaluate(make_spec(risk="read")) == PolicyDecision.ALLOW


# ── Risk: write ───────────────────────────────────────────────────────────────

def test_write_risk_requires_confirmation() -> None:
    """write tools require confirmation unless is_approved=True."""
    policy = ToolPolicy()
    assert policy.evaluate(make_spec(risk="write"), is_approved=False) == PolicyDecision.REQUIRE_CONFIRMATION
    assert policy.evaluate(make_spec(risk="write"), is_approved=True) == PolicyDecision.ALLOW


# ── Risk: destructive ─────────────────────────────────────────────────────────

def test_destructive_risk_requires_confirmation() -> None:
    policy = ToolPolicy()
    assert policy.evaluate(make_spec(risk="destructive"), is_approved=False) == PolicyDecision.REQUIRE_CONFIRMATION
    assert policy.evaluate(make_spec(risk="destructive"), is_approved=True) == PolicyDecision.ALLOW


# ── Risk: privileged — not in allowlist ───────────────────────────────────────

def test_privileged_not_in_allowlist_is_denied() -> None:
    policy = ToolPolicy(privileged_allowlist=set())
    assert (
        policy.evaluate(make_spec(risk="privileged", name="code.execute"))
        == PolicyDecision.DENY
    )


def test_privileged_empty_allowlist_is_denied() -> None:
    policy = ToolPolicy()
    # No privileged allowlist entries means every privileged tool is denied
    assert (
        policy.evaluate(make_spec(risk="privileged", name="some.privileged.tool"))
        == PolicyDecision.DENY
    )


# ── Risk: privileged — in allowlist ──────────────────────────────────────────

def test_code_execute_in_allowlist_and_exec_enabled_is_allowed() -> None:
    policy = ToolPolicy(privileged_allowlist={"code.execute"})
    assert (
        policy.evaluate(
            make_spec(risk="privileged", name="code.execute"),
            allow_code_exec=True,
        )
        == PolicyDecision.ALLOW
    )


def test_code_execute_in_allowlist_but_exec_disabled_is_denied() -> None:
    """allow_code_exec=False on the channel must override the allowlist."""
    policy = ToolPolicy(privileged_allowlist={"code.execute"})
    assert (
        policy.evaluate(
            make_spec(risk="privileged", name="code.execute"),
            allow_code_exec=False,
        )
        == PolicyDecision.DENY
    )


def test_other_privileged_in_allowlist_is_allowed() -> None:
    """Non-code.execute privileged tools don't check allow_code_exec."""
    policy = ToolPolicy(privileged_allowlist={"admin.special"})
    assert (
        policy.evaluate(make_spec(risk="privileged", name="admin.special"))
        == PolicyDecision.ALLOW
    )


# ── Runtime allowlist mutation ────────────────────────────────────────────────

def test_allow_privileged_at_runtime() -> None:
    policy = ToolPolicy(privileged_allowlist=set())
    assert (
        policy.evaluate(make_spec(risk="privileged", name="my.tool"))
        == PolicyDecision.DENY
    )
    policy.allow_privileged("my.tool")
    assert (
        policy.evaluate(make_spec(risk="privileged", name="my.tool"))
        == PolicyDecision.ALLOW
    )


def test_deny_privileged_removes_from_allowlist() -> None:
    policy = ToolPolicy(privileged_allowlist={"my.tool"})
    policy.deny_privileged("my.tool")
    assert (
        policy.evaluate(make_spec(risk="privileged", name="my.tool"))
        == PolicyDecision.DENY
    )
