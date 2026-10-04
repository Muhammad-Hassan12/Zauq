from __future__ import annotations
import asyncio
import time
import logging
import json
from jsonschema import Draft202012Validator
from backend.security.sanitizer import sanitize_object, sanitize_secrets
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

    Execution failures return a ToolResult. Cancellation propagates so the
    request deadline can stop work and handlers can complete their cleanup.

    This class is stateless between calls and safe to use concurrently.
    """

    def __init__(self, registry: ToolRegistry, policy: ToolPolicy) -> None:
        self._registry = registry
        self._policy = policy

    @property
    def registry(self):
        return self._registry

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
        allowed_tools: set[str] | None = None,
        automatic: bool = False,
        auto_code_test_mode: str = 'off',
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

        # Step 1: Resolve tool
        spec = self._registry.get(tool_name)
        if spec is None:
            logger.warning(f"{run_tag}{call_tag}tool={tool_name} status=unknown_tool duration=0ms")
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: '{tool_name}'",
                duration_ms=0,
                metadata={"dispatched": False},
            )

        if allowed_tools is not None and spec.name not in allowed_tools:
            return ToolResult(tool_name=spec.name, success=False, error='Tool is outside the request allowlist', metadata={"dispatched": False})
        try:
            if not isinstance(arguments, dict):
                raise ValueError('Arguments must be an object')
            Draft202012Validator(spec.input_schema).validate(arguments)
        except Exception:
            return ToolResult(tool_name=spec.name, success=False, error='Invalid tool arguments: schema validation failed', metadata={"dispatched": False})

        # Step 2: Policy check
        decision = self._policy.evaluate(
            spec,
            allow_code_exec=allow_code_exec,
            guild_id=guild_id,
            is_approved=is_approved,
            automatic=automatic,
            auto_code_test_mode=auto_code_test_mode,
        )
        elapsed = int((time.monotonic() - start) * 1000)

        if decision == PolicyDecision.DENY:
            logger.warning(f"{run_tag}{call_tag}tool={spec.name} status=denied duration={elapsed}ms")
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error=f"Tool '{spec.name}' was denied by policy (risk={spec.risk})",
                duration_ms=elapsed,
                metadata={"dispatched": False},
            )

        if decision == PolicyDecision.REQUIRE_CONFIRMATION:
            logger.info(f"{run_tag}{call_tag}tool={spec.name} status=requires_confirmation duration={elapsed}ms")
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error="REQUIRES_CONFIRMATION",
                duration_ms=elapsed,
                metadata={"requires_confirmation": True, "dispatched": False},
            )

        # Step 3: Resolve handler
        handler = self._registry.get_handler(spec.name)
        if handler is None:
            elapsed = int((time.monotonic() - start) * 1000)
            logger.error(f"{run_tag}{call_tag}tool={spec.name} status=no_handler duration={elapsed}ms")
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error=f"No handler registered for '{spec.name}'",
                duration_ms=elapsed,
                metadata={"dispatched": False},
            )

        # Step 4: Execute with timeout
        try:
            raw = await asyncio.wait_for(
                handler(arguments),
                timeout=spec.timeout_seconds,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            result = raw if isinstance(raw, ToolResult) else ToolResult(
                tool_name=spec.name,
                success=True,
                content=raw,
                duration_ms=duration_ms,
            )
            result.tool_name = spec.name
            result.duration_ms = duration_ms
            result.content = sanitize_object(result.content)
            result.error = sanitize_secrets(result.error)
            result.metadata = sanitize_object(result.metadata)
            result.metadata['dispatched'] = True
            if isinstance(raw, dict) and (raw.get('success') is False or raw.get('error')):
                result.success = False
                result.error = sanitize_secrets(str(raw.get('error') or 'Tool reported failure'))
            serialized = json.dumps(result.content, default=str, ensure_ascii=False)
            if len(serialized) > settings.SANDBOX_MAX_OUTPUT_CHARS:
                result.content = (serialized[:max(0, settings.SANDBOX_MAX_OUTPUT_CHARS-19)] + '\n[Output truncated]')[:settings.SANDBOX_MAX_OUTPUT_CHARS]
                result.metadata['truncated'] = True

            logger.info(
                f"{run_tag}{call_tag}tool={spec.name} status={'ok' if result.success else 'error'} duration={duration_ms}ms"
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
                metadata={"dispatched": True},
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.error(
                f"{run_tag}{call_tag}tool={spec.name} status=error duration={duration_ms}ms error={sanitize_secrets(str(exc))}"
            )
            return ToolResult(
                tool_name=spec.name,
                success=False,
                error=sanitize_secrets(str(exc)),
                duration_ms=duration_ms,
                metadata={"dispatched": True},
            )


from backend.tools.registry import tool_registry
from backend.tools.policy import tool_policy

# Module-level singleton
tool_executor = ToolExecutor(registry=tool_registry, policy=tool_policy)
