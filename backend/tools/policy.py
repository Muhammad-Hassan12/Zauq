from __future__ import annotations
import logging
from enum import Enum
from backend.tools.base import ToolSpec, RiskLevel

logger = logging.getLogger("zauq.tools.policy")


class PolicyDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"


class ToolPolicy:
    """
    Evaluates whether a tool call should proceed.

    SECURITY INVARIANT: The LLM is never the security authority.
    ToolPolicy always runs before ToolExecutor calls any handler.

    Risk level semantics (Phase 1):
      read        -> auto-allowed
      write       -> DENY (Phase 7 will upgrade to REQUIRE_CONFIRMATION)
      destructive -> DENY always
      privileged  -> DENY unless in the explicit allowlist AND channel permission
                     is satisfied

    The default module-level singleton includes "code.execute" in the
    privileged allowlist, but it still requires allow_code_exec=True from
    the channel profile to actually execute.
    """

    # Auto-denied in Phase 1. Phase 7 will add the approval flow for "write".
    _BLOCKED: frozenset[RiskLevel] = frozenset({"write", "destructive"})

    def __init__(self, privileged_allowlist: set[str] | None = None) -> None:
        """
        Args:
            privileged_allowlist: Set of canonical tool names that are permitted
                to run despite being "privileged" risk, subject to any additional
                per-tool checks (e.g. allow_code_exec for code.execute).
        """
        self._privileged_allowlist: set[str] = privileged_allowlist or set()

    def evaluate(
        self,
        spec: ToolSpec,
        *,
        allow_code_exec: bool = False,
        guild_id: str | None = None,
        is_approved: bool = False,
    ) -> PolicyDecision:
        """
        Return the policy decision for this tool call.

        Args:
            spec:            The ToolSpec to evaluate.
            allow_code_exec: Channel-level permission for code execution.
                             Only relevant for "code.execute".
            guild_id:        Discord guild ID of the requesting context.
            is_approved:     Whether human approval has already been granted.
        """
        # Disabled tool — never run
        if not spec.enabled:
            logger.warning(f"Policy DENY: tool '{spec.name}' is disabled")
            return PolicyDecision.DENY

        # Guild access scope check (e.g. MCP tools restricted to specific guilds)
        if spec.allowed_guild_ids:
            if not guild_id or guild_id not in spec.allowed_guild_ids:
                logger.warning(
                    f"Policy DENY: tool '{spec.name}' is scoped to guilds {spec.allowed_guild_ids}, "
                    f"current guild is '{guild_id}'"
                )
                return PolicyDecision.DENY

        # Phase 7: Side-effect confirmation flow for write and destructive tools
        if spec.risk in ("write", "destructive"):
            if is_approved:
                logger.info(f"Policy ALLOW: tool '{spec.name}' (risk={spec.risk}) explicitly approved by user.")
                return PolicyDecision.ALLOW
            logger.info(
                f"Policy REQUIRE_CONFIRMATION: tool '{spec.name}' risk='{spec.risk}' "
                "staged for human approval."
            )
            return PolicyDecision.REQUIRE_CONFIRMATION

        # Privileged: must be in allowlist and pass any per-tool checks
        if spec.risk == "privileged":
            if spec.name not in self._privileged_allowlist:
                logger.warning(
                    f"Policy DENY: tool '{spec.name}' is privileged but "
                    "not in the privileged allowlist"
                )
                return PolicyDecision.DENY

            # code.execute additionally requires channel-level permission
            if spec.name == "code.execute" and not allow_code_exec:
                logger.warning(
                    "Policy DENY: code.execute is in privileged allowlist but "
                    "allow_code_exec=False for this channel"
                )
                return PolicyDecision.DENY

            return PolicyDecision.ALLOW

        # risk == "read" -> allow
        return PolicyDecision.ALLOW

    def allow_privileged(self, tool_name: str) -> None:
        """Add a canonical tool name to the privileged allowlist at runtime."""
        self._privileged_allowlist.add(tool_name)
        logger.debug(f"Added '{tool_name}' to privileged allowlist")

    def deny_privileged(self, tool_name: str) -> None:
        """Remove a tool from the privileged allowlist."""
        self._privileged_allowlist.discard(tool_name)


# Module-level singleton.
# code.execute is in the allowlist but still requires allow_code_exec=True per channel.
tool_policy = ToolPolicy(privileged_allowlist={"code.execute"})
