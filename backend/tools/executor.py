from __future__ import annotations
import asyncio
import time
import logging
from backend.tools.base import ToolResult
from backend.tools.policy import ToolPolicy, PolicyDecision
from backend.tools.registry import ToolRegistry
from backend.config import settings

logger = logging.getLogger("zauq.tools.executor")


class ToolExecutor:
    """
    Executes tools through the full pipeline:

        registry lookup
            -> policy evaluation
            -> async handler with timeout
            -> output truncation
            -> ToolResult

    GUARANTEE: execute() always returns a ToolResult and never raises.
    Callers do not need try/except around executor.execute().

    This class is stateless between calls and safe to use concurrently.
    """

    def __init__(self, registry: ToolRegistry, policy: ToolPolicy) -> None:
        self._registry = registry
        self._policy = policy

    async def execute(
        self,
        tool_name: str,
        arguments: dict,
        *,
        allow_code_exec: bool = False,
        guild_id: str | None = None,
        is_approved: bool = False,
        agent_run_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> ToolResult:
        """
        Execute a tool by canonical name or provider alias.

        Args:
            tool_name:       Canonical name ("web.search") or alias ("web__search").
            arguments:       Validated argument dict for the tool handler.
            allow_code_exec: Channel-level flag forwarded to policy for code.execute.
            guild_id:        Discord guild ID forwarded to policy for scope checking.
            is_approved:     Whether human approval has already been granted.
            agent_run_id:    Phase 11 execution ID for structured telemetry.
            tool_call_id:    Phase 11 tool call ID for structured telemetry.

        Returns:
            ToolResult with success=True on success, success=False on any failure.
        """
        start = time.monotonic()
        run_tag = f"agent_run={agent_run_id} " if agent_run_id else ""
        call_tag = f"tool_call_id={tool_call_id} " if tool_call_id else ""

        # ── Step 1: Resolve tool ─────────────────────────────────────────────
        spec = self._registry.get(tool_name)
        if spec is None:
            logger.warning(f"{run_tag}{call_tag}tool={tool_name} status=unknown_tool duration=0ms")
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: '{tool_name}'",
                duration_ms=0,
            )

        # ── Step 2: Policy check ─────────────────────────────────────────────
        decision = self._policy.evaluate(
            spec,
            allow_code_exec=allow_code_exec,
            guild_id=guild_id,
            is_approved=is_approved,
        )
        elapsed = int((time.monotonic() - start) * 1000)

        if decision == PolicyDecision.DENY:
            logger.warning(f"{run_tag}{call_tag}tool={spec.name} status=denied duration={elapsed}ms")
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error=f"Tool '{spec.name}' was denied by policy (risk={spec.risk})",
                duration_ms=elapsed,
            )

        if decision == PolicyDecision.REQUIRE_CONFIRMATION:
            logger.info(f"{run_tag}{call_tag}tool={spec.name} status=requires_confirmation duration={elapsed}ms")
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error="REQUIRES_CONFIRMATION",
                duration_ms=elapsed,
                metadata={"requires_confirmation": True},
            )

        # ── Step 3: Resolve handler ──────────────────────────────────────────
        handler = self._registry.get_handler(spec.name)
        if handler is None:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error(f"{run_tag}{call_tag}tool={spec.name} status=no_handler duration={elapsed}ms")
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error=f"No handler registered for '{spec.name}'",
                duration_ms=elapsed,
            )

        # ── Step 4: Execute with timeout ─────────────────────────────────────
        try:
            raw = await asyncio.wait_for(
                handler(arguments),
                timeout=spec.timeout_seconds,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            result = ToolResult(
                tool_name=spec.name,
                success=True,
                content=raw,
                duration_ms=duration_ms,
            )

            # ── Step 5: Validate output size ─────────────────────────────────
            result.as_text(max_chars=settings.SANDBOX_MAX_OUTPUT_CHARS)

            logger.info(
                f"{run_tag}{call_tag}tool={spec.name} status=ok duration={duration_ms}ms"
            )
            return result

        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                f"{run_tag}{call_tag}tool={spec.name} status=timeout timeout_s={spec.timeout_seconds} duration={duration_ms}ms"
            )
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error=f"Tool timed out after {spec.timeout_seconds}s",
                duration_ms=duration_ms,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                f"{run_tag}{call_tag}tool={spec.name} status=error duration={duration_ms}ms error={exc}"
            )
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error=str(exc),
                duration_ms=duration_ms,
            )


from backend.tools.registry import tool_registry
from backend.tools.policy import tool_policy

# Module-level singleton
tool_executor = ToolExecutor(registry=tool_registry, policy=tool_policy)
