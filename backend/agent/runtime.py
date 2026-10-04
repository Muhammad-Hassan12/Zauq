from __future__ import annotations
import json
import logging
import time
import uuid
import hashlib
import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from backend.agent.limits import (
    AgentBudget,
    NORMAL_MAX_TOOL_STEPS,
    DEEP_MAX_TOOL_STEPS,
    GLOBAL_MAX_TOOL_STEPS,
)
from backend.agent.types import AgentModelTurn, ToolCall, ToolResultMessage
from backend.config import settings
from backend.agent.deadlines import bounded_runtime
from backend.models.router import model_router, ModelRouter
from backend.tools.base import ToolSpec, ToolResult
from backend.tools.executor import tool_executor, ToolExecutor
from backend.security.sanitizer import sanitize_secrets
from backend.security.prompt_guard import PROMPT_INJECTION_DIRECTIVE, fence_tool_data

logger = logging.getLogger("zauq.agent.runtime")


def extract_turn_usage(raw_meta: dict[str, Any]) -> tuple[int | None, int | None]:
    """Extract (input_tokens, output_tokens) from raw provider response metadata."""
    if not raw_meta:
        return (None, None)
    usage_meta = raw_meta.get("usageMetadata")
    if usage_meta and isinstance(usage_meta, dict):
        in_t = usage_meta.get("promptTokenCount")
        out_t = usage_meta.get("candidatesTokenCount")
        return (in_t, out_t)
    usage = raw_meta.get("usage")
    if usage and isinstance(usage, dict):
        in_t = usage.get("prompt_tokens") or usage.get("input_tokens")
        out_t = usage.get("completion_tokens") or usage.get("output_tokens")
        return (in_t, out_t)
    return (None, None)


@dataclass
class ToolTraceItem:
    """Record of a single tool execution for request metadata."""
    tool: str
    success: bool
    duration_ms: int
    error: Optional[str] = None
    requires_confirmation: bool = False
    action_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "tool": self.tool,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }
        if self.requires_confirmation:
            d["requires_confirmation"] = True
            d["action_id"] = self.action_id
        return d


@dataclass
class AgentRunResult:
    """Outcome of an agent runtime execution."""
    final_response: str
    tool_trace: List[Dict[str, Any]] = field(default_factory=list)
    tool_steps: int = 0
    model_turns: int = 0
    budget_exhausted: bool = False
    loop_detected: bool = False
    search_calls: int = 0
    pages_fetched: int = 0
    sandbox_calls: int = 0
    mcp_calls: int = 0
    tool_failures: int = 0
    duration_ms: int = 0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    agent_run_id: Optional[str] = None
    incomplete: bool = False


class AgentRuntime:
    """Bounded, state-machine agent runtime for tool execution."""

    def __init__(
        self,
        router: Optional[ModelRouter] = None,
        executor: Optional[ToolExecutor] = None,
    ) -> None:
        self.router = router or model_router
        self.executor = executor or tool_executor

    @bounded_runtime
    async def run(
        self,
        messages: List[Dict[str, Any]],
        provider: str,
        model_name: str,
        system_prompt: str,
        temperature: float = 0.7,
        media_parts: Optional[List[Dict[str, str]]] = None,
        tools: Optional[List[ToolSpec]] = None,
        max_steps: Optional[int] = None,
        channel_id: Optional[str] = None,
        user_id: Optional[str] = None,
        guild_id: Optional[str] = None,
        operating_mode: str = "hangout",
        allow_code_exec: bool = False,
        auto_code_test_mode: str = "off",
        thinking_enabled: bool = False,
        deep_search: bool = False,
    ) -> AgentRunResult:
        """Run the bounded agent loop to completion.

        Args:
            messages: Input conversation history.
            provider: LLM provider name.
            model_name: Specific model name.
            system_prompt: Base persona / instructions.
            temperature: Sampling temperature.
            media_parts: Attached images/audio if any.
            tools: Selected candidate tools (or None/empty).
            max_steps: Step cap override (bounded by GLOBAL_MAX_TOOL_STEPS).
            channel_id: Context channel ID.
            user_id: Requesting user ID.
            guild_id: Context guild ID.
            operating_mode: 'dev' or 'hangout'.
            allow_code_exec: Channel permission for code execution.
            auto_code_test_mode: 'off', 'auto', or 'always'.
            thinking_enabled: Gemini reasoning mode flag.
            deep_search: Deep search mode flag.

        Returns:
            AgentRunResult with final response, tool trace, and step count.
        """
        start_time = time.monotonic()
        agent_run_id = f"run_{uuid.uuid4().hex[:8]}"
        total_input_tokens: Optional[int] = None
        total_output_tokens: Optional[int] = None

        # Ensure prompt injection defense is present in system prompt (Phase 12)
        if PROMPT_INJECTION_DIRECTIVE not in system_prompt:
            system_prompt = f"{system_prompt}\n\n[SECURITY POLICY]: {PROMPT_INJECTION_DIRECTIVE}"

        # If no tools are available or selected, execute single direct generation turn
        if not tools:
            logger.debug("No tools provided to AgentRuntime. Executing direct model turn.")
            response_text = await self.router.generate(
                messages=messages,
                provider=provider,
                model_name=model_name,
                system_prompt=system_prompt,
                temperature=temperature,
                media_parts=media_parts,
                thinking_enabled=thinking_enabled,
            )
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            return AgentRunResult(
                final_response=sanitize_secrets(response_text),
                tool_trace=[],
                tool_steps=0,
                model_turns=1,
                agent_run_id=agent_run_id,
                duration_ms=elapsed_ms,
            )

        # 1. Initialize budget
        if max_steps is None:
            max_steps = settings.AGENT_DEEP_MAX_TOOL_STEPS if deep_search else settings.AGENT_MAX_TOOL_STEPS
        configured_max = settings.AGENT_DEEP_MAX_TOOL_STEPS if deep_search else settings.AGENT_MAX_TOOL_STEPS
        effective_max = max(0, min(max_steps, configured_max, GLOBAL_MAX_TOOL_STEPS))
        budget = AgentBudget(max_tool_steps=effective_max,
                             max_search_calls=3 if deep_search else 2,
                             max_pages_fetched=5 if deep_search else 3,
                             max_sandbox_calls=1 + max(0, min(settings.AUTO_CODE_REPAIR_ATTEMPTS, 1)))

        working_messages: List[Dict[str, Any]] = copy.deepcopy(messages)
        tools = list(tools)
        selected_specs = {t.name:t for t in tools}
        tool_traces: List[Dict[str, Any]] = []
        call_signatures_seen: Set[str] = set()
        model_turns = 0
        code_repair_attempts_used = 0
        loop_detected = False
        def partial_result(text):
            return AgentRunResult(final_response=sanitize_secrets(text), tool_trace=tool_traces,
                                  tool_steps=budget.tool_steps_used, model_turns=model_turns,
                                  search_calls=budget.search_calls_used, pages_fetched=budget.pages_fetched_used,
                                  sandbox_calls=budget.sandbox_calls_used, mcp_calls=budget.mcp_calls_used,
                                  tool_failures=budget.tool_failures_used, duration_ms=int((time.monotonic()-start_time)*1000),
                                  input_tokens=total_input_tokens, output_tokens=total_output_tokens,
                                  agent_run_id=agent_run_id, incomplete=True)

        logger.debug(
            f"Starting AgentRuntime with provider='{provider}', model='{model_name}', "
            f"tools={[t.name for t in tools]}, max_steps={budget.max_tool_steps}, agent_run={agent_run_id}"
        )

        # 2. Main Bounded Loop
        while not budget.is_exhausted():
            model_turns += 1

            try:
                turn: AgentModelTurn = await self.router.generate_agent_turn(
                messages=working_messages,
                tools=tools,
                provider=provider,
                model_name=model_name,
                system_prompt=system_prompt,
                temperature=temperature,
                media_parts=media_parts,
                thinking_enabled=thinking_enabled,
                )
            except Exception:
                if tool_traces:
                    return partial_result('The selected provider failed after tool activity. The run stopped without replaying actions; completed tool results are shown in the trace.')
                raise
            if len(turn.tool_calls) > GLOBAL_MAX_TOOL_STEPS:
                return partial_result('The model requested too many simultaneous tool calls. No calls from that batch were executed.')

            # Accumulate token metrics if provider reports usage
            in_t, out_t = extract_turn_usage(turn.raw_metadata)
            if in_t is not None:
                total_input_tokens = (total_input_tokens or 0) + in_t
            if out_t is not None:
                total_output_tokens = (total_output_tokens or 0) + out_t

            # If model produced final text and no tool calls -> we are done!
            if not turn.has_tool_calls:
                elapsed_ms = int((time.monotonic() - start_time) * 1000)
                logger.debug(f"Model concluded with final answer on turn {model_turns} (agent_run={agent_run_id}).")
                return AgentRunResult(
                    final_response=sanitize_secrets(turn.text or ""),
                    tool_trace=tool_traces,
                    tool_steps=budget.tool_steps_used,
                    model_turns=model_turns,
                    budget_exhausted=False,
                    loop_detected=loop_detected,
                    search_calls=budget.search_calls_used,
                    pages_fetched=budget.pages_fetched_used,
                    sandbox_calls=budget.sandbox_calls_used,
                    mcp_calls=budget.mcp_calls_used,
                    tool_failures=budget.tool_failures_used,
                    duration_ms=elapsed_ms,
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                    agent_run_id=agent_run_id,
                )

            # Model requested one or more tool calls
            # Append model's assistant turn to history
            working_messages.append({
                "role": "assistant",
                "content": turn.text or "",
                "tool_calls": turn.tool_calls,
                '_provider_continuation':copy.deepcopy(turn.provider_continuation),
            })

            # Process each requested tool call
            for call in turn.tool_calls:
                from backend.tools.aliases import canonical_to_alias
                matching = next((t for t in tools if call.name in (t.name, canonical_to_alias(t.name))), None)
                if matching:
                    call.name = matching.name

                # Signature for loop detection (same tool + same arguments)
                try:
                    norm_args = json.dumps(call.arguments, sort_keys=True)
                except Exception:
                    norm_args = str(call.arguments)
                call_sig = f"{call.name}:{norm_args}"

                # ── Loop Detection ───────────────────────────────────────────
                if call_sig in call_signatures_seen:
                    logger.warning('Duplicate call blocked tool=%s digest=%s', call.name, hashlib.sha256(call_sig.encode()).hexdigest()[:12])
                    loop_detected = True
                    budget.tool_failures_used += 1
                    tool_traces.append(
                        ToolTraceItem(
                            tool=call.name,
                            success=False,
                            duration_ms=0,
                            error="duplicate_call_detected",
                        ).to_dict()
                    )
                    error_observation = (
                        f"Error: Tool '{call.name}' was already called with identical arguments. "
                        "Please synthesize your answer using the existing observations or call a different tool."
                    )
                    working_messages.append(
                        ToolResultMessage(
                            tool_call_id=call.id,
                            tool_name=call.name,
                            content=error_observation,
                            is_error=True,
                            provider_call_id=call.provider_call_id,
                        ).to_dict()
                    )
                    if not budget.is_exhausted():
                        budget.tool_steps_used += 1
                    continue

                call_signatures_seen.add(call_sig)

                # ── Tool Execution ───────────────────────────────────────────
                exec_kwargs = {
                    "tool_name": call.name,
                    "arguments": call.arguments,
                    "allow_code_exec": allow_code_exec,
                    "agent_run_id": agent_run_id,
                    "tool_call_id": call.id,
                    'allowed_tools':{t.name for t in tools},
                    'automatic':True,
                    'auto_code_test_mode':auto_code_test_mode,
                }
                if guild_id is not None:
                    exec_kwargs["guild_id"] = guild_id
                blocked = not matching or budget.is_exhausted()
                blocked = blocked or (call.name == 'web.search' and not budget.can_search())
                blocked = blocked or (call.name == 'web.fetch' and not budget.can_fetch_page())
                blocked = blocked or (call.name == 'code.execute' and (not budget.can_use_sandbox() or not allow_code_exec or auto_code_test_mode == 'off'))
                blocked = blocked or (matching is not None and matching.source == 'mcp' and not budget.can_use_mcp())
                if blocked:
                    tool_res = ToolResult(call.name, False, error='Request policy or resource budget prohibits this call')
                else:
                    tool_res = await self.executor.execute(**exec_kwargs)
                if not budget.is_exhausted():
                    budget.tool_steps_used += 1
                dispatched = not blocked and tool_res.metadata.get('dispatched', True)
                if dispatched and call.name == "web.search":
                    content = tool_res.content if isinstance(tool_res.content, dict) else {}
                    budget.search_calls_used += content.get('search_calls', int(not content.get('from_cache', False)))
                elif dispatched and call.name == "web.fetch":
                    budget.page_fetch_attempts += 1
                    budget.pages_fetched_used += int(tool_res.success)
                elif dispatched and call.name == "code.execute":
                    budget.sandbox_calls_used += 1
                elif dispatched and matching and matching.source == 'mcp':
                    budget.mcp_calls_used += 1

                if not tool_res.success and not tool_res.metadata.get('requires_confirmation'):
                    budget.tool_failures_used += 1

                pending_action_id = None
                requires_conf = bool(tool_res.metadata.get("requires_confirmation"))

                if requires_conf:
                    try:
                        from backend.actions.service import action_service
                        spec_obj = selected_specs.get(call.name)
                        action_risk = getattr(spec_obj, "risk", "write") if spec_obj else "write"
                        act = await action_service.create_action(
                            channel_id=channel_id or "unknown",
                            user_id=user_id or "unknown",
                            tool_name=call.name,
                            arguments=call.arguments,
                            guild_id=guild_id,
                            risk=action_risk,
                        )
                        pending_action_id = act.action_id
                        obs_content = (
                            f"[Human Confirmation Required: Action ID '{act.action_id}'. "
                            f"Tool '{call.name}' has side-effects (risk='{action_risk}') and has been staged. "
                            "Do not retry calling this tool. "
                            "Explain what action was prepared and ask the user to approve or deny using the confirmation buttons.]"
                        )
                    except Exception as act_err:
                        logger.warning('Failed to create pending action (%s)', type(act_err).__name__)
                        obs_content = f"Tool '{call.name}' requires confirmation, but action storage is unavailable. Nothing was executed."
                elif tool_res.success:
                    obs_content = tool_res.as_text()
                else:
                    obs_content = f"Tool '{call.name}' failed: {tool_res.error}"

                # Enforce Phase 12 Security Hardening:
                # 1. Output size capping before context injection
                max_tool_chars = getattr(settings, "SANDBOX_MAX_OUTPUT_CHARS", 12000)
                if len(obs_content) > max_tool_chars:
                    obs_content = obs_content[:max_tool_chars] + f"\n... [Output truncated at {max_tool_chars:,} characters]"

                # 2. Secret scrubbing from model context
                obs_content = sanitize_secrets(obs_content)

                # 3. Untrusted tool data fencing (unless confirmation prompt)
                if not requires_conf:
                    obs_content = fence_tool_data(call.name, obs_content)

                tool_traces.append(
                    ToolTraceItem(
                        tool=call.name,
                        success=tool_res.success,
                        duration_ms=tool_res.duration_ms,
                        error=sanitize_secrets(tool_res.error),
                        requires_confirmation=requires_conf,
                        action_id=pending_action_id,
                    ).to_dict()
                )

                # Enforce Phase 5 Repair Loop: max 1 repair attempt for code.execute
                if call.name == "code.execute":
                    is_failure = not tool_res.success
                    if isinstance(tool_res.content, dict) and tool_res.content.get("exit_code", 0) != 0:
                        is_failure = True
                    repairs = max(0, min(settings.AUTO_CODE_REPAIR_ATTEMPTS, 1))
                    if budget.sandbox_calls_used >= 1:
                        if not is_failure or budget.sandbox_calls_used >= 1 + repairs:
                            tools = [t for t in tools if t.name != 'code.execute']
                            obs_content += '\n[Sandbox verification finished; no further code execution is permitted.]'
                        else:
                            obs_content += '\n[One corrected verification attempt is available. Explain the observed failure honestly.]'

                working_messages.append(
                    ToolResultMessage(
                        tool_call_id=call.id,
                        tool_name=call.name,
                        content=obs_content,
                        is_error=not tool_res.success,
                        provider_call_id=call.provider_call_id,
                    ).to_dict()
                )

        # 3. Budget Exhausted: Run one final synthesis turn without tools
        logger.info(
            f"Agent loop reached step limit ({budget.tool_steps_used}/{budget.max_tool_steps}). "
            f"Requesting final synthesis (agent_run={agent_run_id})."
        )
        model_turns += 1
        try:
            final_answer = await self.router.generate(
            messages=working_messages,
            provider=provider,
            model_name=model_name,
            system_prompt=system_prompt,
            temperature=temperature,
            media_parts=media_parts,
            thinking_enabled=thinking_enabled,
            )
        except Exception:
            if tool_traces:
                return partial_result('The provider could not synthesize the completed tool results. No actions were replayed.')
            raise

        elapsed_ms = int((time.monotonic() - start_time) * 1000)
        return AgentRunResult(
            final_response=sanitize_secrets(final_answer),
            tool_trace=tool_traces,
            tool_steps=budget.tool_steps_used,
            model_turns=model_turns,
            budget_exhausted=True,
            loop_detected=loop_detected,
            search_calls=budget.search_calls_used,
            pages_fetched=budget.pages_fetched_used,
            sandbox_calls=budget.sandbox_calls_used,
            mcp_calls=budget.mcp_calls_used,
            tool_failures=budget.tool_failures_used,
            duration_ms=elapsed_ms,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            agent_run_id=agent_run_id,
        )


# Global singleton
agent_runtime = AgentRuntime()
