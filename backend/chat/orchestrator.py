"""Chat Orchestrator for Zauq.

Dispatches chat completions between:
1. Legacy v3 Direct Generation (when AGENT_RUNTIME_ENABLED=False)
2. v4 Bounded Agent Runtime (when AGENT_RUNTIME_ENABLED=True)

Maintains full backward compatibility for responses, fallback logic,
file extractions, metrics, and episodic memory background workers.
"""

from __future__ import annotations
import re
import time
import uuid
import asyncio
import logging
from typing import Any, Dict, Optional
from fastapi import BackgroundTasks

from backend.config import settings
from backend.models.router import model_router
from backend.agent.runtime import agent_runtime, AgentRunResult
from backend.agent.capability_router import capability_router
from backend.chat.context_builder import context_builder, ChatContext
from backend.parsers.file_parser import extract_generated_files
from backend.integrations.web_search import web_search_engine
from backend.search.service import search_service
from backend.memory.metrics import log_request_metric
from backend.memory.episodic import extract_and_store_user_memories
from backend.security.sanitizer import sanitize_secrets

logger = logging.getLogger("zauq.chat.orchestrator")


class ChatOrchestrator:
    """Orchestrates chat requests across context building, agent runtime, and model fallbacks."""

    def __init__(
        self,
        context_builder_inst: Optional[ChatContextBuilder] = None,
        router: Optional[Any] = None,
        runtime: Optional[AgentRuntime] = None,
        cap_router: Optional[CapabilityRouter] = None,
    ) -> None:
        self.context_builder = context_builder_inst or context_builder
        self.model_router = router or model_router
        self.agent_runtime = runtime or agent_runtime
        self.capability_router = cap_router or capability_router

    async def run(self, req: Any, background_tasks: BackgroundTasks) -> Dict[str, Any]:
        """Execute chat completion request."""
        start_time = time.time()
        request_id = f"req_{uuid.uuid4().hex[:10]}"
        ctx: ChatContext = await self.context_builder.build(req)

        provider = ctx.provider
        model_name = ctx.model_name
        original_provider = provider
        original_model = model_name
        was_fallback = False

        tool_trace = []
        tool_steps = 0
        search_calls = 0
        pages_fetched = 0
        sandbox_calls = 0
        mcp_calls = 0
        tool_failures = 0
        input_tokens: Optional[int] = None
        output_tokens: Optional[int] = None
        agent_run_id: Optional[str] = None
        agent_duration_ms: Optional[int] = None

        # ── Route Path: Bounded Agent Runtime (v4) ───────────────────────────
        if settings.AGENT_RUNTIME_ENABLED:
            logger.debug("Executing request via v4 Bounded Agent Runtime.")
            selected_tools = self.capability_router.select_tools(
                messages=ctx.working_messages,
                provider=provider,
                model_name=model_name,
                enable_web_search=req.enable_web_search,
                deep_search=bool(req.deep_search),
                search_query=req.search_query,
                allow_code_exec=ctx.allow_code_exec,
                auto_code_test_mode=ctx.auto_code_test_mode,
                guild_id=req.guild_id,
            )

            try:
                run_res: AgentRunResult = await self.agent_runtime.run(
                    messages=ctx.working_messages,
                    provider=provider,
                    model_name=model_name,
                    system_prompt=ctx.persona,
                    temperature=ctx.temperature,
                    media_parts=ctx.media_parts,
                    tools=selected_tools,
                    channel_id=req.channel_id,
                    user_id=req.user_id,
                    guild_id=req.guild_id,
                    operating_mode=ctx.mode,
                    allow_code_exec=ctx.allow_code_exec,
                    auto_code_test_mode=ctx.auto_code_test_mode,
                    thinking_enabled=ctx.thinking_enabled,
                    deep_search=bool(req.deep_search),
                )
                raw_response_text = run_res.final_response
                tool_trace = run_res.tool_trace
                tool_steps = run_res.tool_steps
                search_calls = run_res.search_calls
                pages_fetched = run_res.pages_fetched
                sandbox_calls = run_res.sandbox_calls
                mcp_calls = run_res.mcp_calls
                tool_failures = run_res.tool_failures
                input_tokens = run_res.input_tokens
                output_tokens = run_res.output_tokens
                agent_run_id = run_res.agent_run_id
                agent_duration_ms = run_res.duration_ms
            except Exception as runtime_err:
                # Graceful fallback to Gemini if secondary provider fails
                if provider != "gemini" and settings.GEMINI_API_KEY:
                    logger.warning(
                        f"Agent runtime failed with provider '{provider}' ({runtime_err}). "
                        "Falling back to Gemini 2.5 Flash."
                    )
                    provider = "gemini"
                    model_name = "gemini-2.5-flash"
                    was_fallback = True

                    gemini_tools = self.capability_router.select_tools(
                        messages=ctx.working_messages,
                        provider="gemini",
                        model_name="gemini-2.5-flash",
                        enable_web_search=req.enable_web_search,
                        deep_search=bool(req.deep_search),
                        search_query=req.search_query,
                        allow_code_exec=ctx.allow_code_exec,
                        auto_code_test_mode=ctx.auto_code_test_mode,
                        guild_id=req.guild_id,
                    )
                    run_res = await self.agent_runtime.run(
                        messages=ctx.working_messages,
                        provider="gemini",
                        model_name="gemini-2.5-flash",
                        system_prompt=ctx.persona,
                        temperature=ctx.temperature,
                        media_parts=ctx.media_parts,
                        tools=gemini_tools,
                        channel_id=req.channel_id,
                        user_id=req.user_id,
                        guild_id=req.guild_id,
                        operating_mode=ctx.mode,
                        allow_code_exec=ctx.allow_code_exec,
                        auto_code_test_mode=ctx.auto_code_test_mode,
                        thinking_enabled=ctx.thinking_enabled,
                        deep_search=bool(req.deep_search),
                    )
                    raw_response_text = run_res.final_response
                    tool_trace = run_res.tool_trace
                    tool_steps = run_res.tool_steps
                    search_calls = run_res.search_calls
                    pages_fetched = run_res.pages_fetched
                    sandbox_calls = run_res.sandbox_calls
                    mcp_calls = run_res.mcp_calls
                    tool_failures = run_res.tool_failures
                    input_tokens = run_res.input_tokens
                    output_tokens = run_res.output_tokens
                    agent_run_id = run_res.agent_run_id
                    agent_duration_ms = run_res.duration_ms
                else:
                    raise runtime_err

        # ── Route Path: Legacy v3 Generation (Backward Compatibility) ─────────
        else:
            logger.debug("Executing request via v3 Direct Generation path.")
            # 1. Scrape URLs in user message
            if ctx.working_messages:
                target_user_msg = next((m for m in reversed(ctx.working_messages) if m.get("role") == "user"), ctx.working_messages[-1])
                urls = web_search_engine.extract_urls(target_user_msg.get("content", ""))
                for u in urls[:2]:
                    try:
                        page_text = await web_search_engine.fetch_url_content(u, max_chars=5000)
                        if page_text and not page_text.startswith("[Failed"):
                            target_user_msg["content"] += f"\n\n[Attached Live Webpage Content for {u}]:\n{page_text}"
                    except Exception as url_err:
                        logger.info(f"URL scrape failed for {u}: {url_err}")

            # 2. Enrich context with web search roaming if requested
            if ctx.working_messages and (req.deep_search or req.enable_web_search or (req.search_category and req.search_category != "all")):
                target_user_msg = next((m for m in reversed(ctx.working_messages) if m.get("role") == "user"), ctx.working_messages[-1])
                user_text = target_user_msg.get("content", "")

                raw_search_q = req.search_query or user_text
                if 'following query: "' in raw_search_q:
                    match = re.search(r'following query:\s*"([^"]+)"', raw_search_q)
                    if match:
                        raw_search_q = match.group(1)
                elif "following query: '" in raw_search_q:
                    match = re.search(r"following query:\s*'([^']+)'", raw_search_q)
                    if match:
                        raw_search_q = match.group(1)

                search_data = await search_service.search_and_fetch(
                    query=raw_search_q,
                    max_results=5,
                    fetch_top_n=5 if req.deep_search else 2,
                    category=req.search_category or "all",
                )
                search_calls += 1
                pages_fetched += len(search_data.get("roamed_pages", []))
                if search_data.get("context_text"):
                    target_user_msg["content"] += (
                        f"\n\n[Autonomous Deep Web Research Context & Live Sources]:\n"
                        f"{search_data['context_text']}\n\n"
                        "Synthesize a well-structured, authoritative, and comprehensive answer strictly utilizing the live research sources provided above. Format citations as verified markdown links (e.g. • [Title](url))."
                    )
                    tool_trace.append({
                        "tool": "web.search",
                        "success": True,
                        "duration_ms": int((time.time() - start_time) * 1000),
                    })
                    tool_steps += 1

            # Prevent secondary search in model_router if context was already enriched
            pass_enable_search = False if tool_steps > 0 else ctx.enable_search

            try:
                raw_response_text = await self.model_router.generate(
                    messages=ctx.working_messages,
                    provider=provider,
                    model_name=model_name,
                    system_prompt=ctx.persona,
                    temperature=ctx.temperature,
                    media_parts=ctx.media_parts,
                    enable_search=pass_enable_search,
                    thinking_enabled=ctx.thinking_enabled,
                )
            except Exception as prov_err:
                if provider != "gemini" and settings.GEMINI_API_KEY:
                    logger.warning(
                        f"Provider '{provider}' failed ({prov_err}). Gracefully falling back to Gemini 2.5 Flash."
                    )
                    provider = "gemini"
                    model_name = "gemini-2.5-flash"
                    was_fallback = True
                    raw_response_text = await self.model_router.generate(
                        messages=ctx.working_messages,
                        provider="gemini",
                        model_name="gemini-2.5-flash",
                        system_prompt=ctx.persona,
                        temperature=ctx.temperature,
                        media_parts=ctx.media_parts,
                        enable_search=pass_enable_search,
                        thinking_enabled=ctx.thinking_enabled,
                    )
                else:
                    raise prov_err

        # Extract generated files from response
        clean_response_text, extracted_files = extract_generated_files(raw_response_text)
        clean_response_text = sanitize_secrets(clean_response_text)
        for f in extracted_files:
            if isinstance(f, dict) and "content" in f and isinstance(f["content"], str):
                f["content"] = sanitize_secrets(f["content"])

        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"request_id={request_id} provider={provider} model={model_name} status=ok duration={duration_ms}ms"
        )
        background_tasks.add_task(
            log_request_metric,
            guild_id=req.guild_id,
            channel_id=req.channel_id,
            user_id=req.user_id,
            tier=1,
            provider=provider,
            model_name=model_name,
            response_time_ms=duration_ms,
            tool_steps=tool_steps,
            search_calls=search_calls,
            pages_fetched=pages_fetched,
            sandbox_calls=sandbox_calls,
            mcp_calls=mcp_calls,
            tool_failures=tool_failures,
            agent_duration_ms=agent_duration_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            request_id=request_id,
            agent_run_id=agent_run_id,
        )

        if req.user_id:
            background_tasks.add_task(
                extract_and_store_user_memories,
                user_id=req.user_id,
                messages=ctx.working_messages + [{"role": "assistant", "content": clean_response_text}],
                provider=provider,
                model_name=model_name,
            )

        resp_payload: Dict[str, Any] = {
            "mode": ctx.mode,
            "provider": provider,
            "model": model_name,
            "response": clean_response_text,
            "files": extracted_files,
            "thinking_enabled": ctx.thinking_enabled,
            "fallback_triggered": was_fallback,
            "original_provider": original_provider if was_fallback else None,
            "original_model": original_model if was_fallback else None,
            "request_id": request_id,
        }

        # Include tool metadata when running in agent mode
        if settings.AGENT_RUNTIME_ENABLED or tool_steps > 0:
            resp_payload["tool_trace"] = tool_trace
            resp_payload["tool_steps"] = tool_steps

        return resp_payload


chat_orchestrator = ChatOrchestrator()
