from __future__ import annotations
import re
import time
import uuid
import asyncio
import logging
from typing import Any, Dict, Optional
from fastapi import BackgroundTasks, HTTPException

from backend.config import settings
from backend.models.router import model_router
from backend.agent.runtime import agent_runtime, AgentRunResult, AgentRuntime
from backend.agent.capability_router import capability_router, CapabilityRouter
from backend.chat.context_builder import context_builder, ChatContext, ChatContextBuilder
from backend.parsers.file_parser import extract_generated_files
from backend.integrations.web_search import web_search_engine
from backend.search.service import search_service
from backend.memory.metrics import log_request_metric
from backend.memory.episodic import extract_and_store_user_memories
from backend.security.sanitizer import sanitize_secrets
from backend.agent.rollout import feature_enabled
from backend.models.capabilities import supports_native_tools
from backend.security.prompt_guard import fence_tool_data

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
        from backend.memory.usage import usage_records
        records = []
        request_id = f"req_{uuid.uuid4().hex[:10]}"
        started = time.monotonic()
        token = usage_records.set(records)
        deep = bool(req.deep_search)
        file_generation = getattr(req, 'file_generation', False) is True
        limit = settings.FILE_GENERATION_TIMEOUT_SECONDS if file_generation else (settings.AGENT_DEEP_RESEARCH_TIMEOUT_SECONDS if deep else settings.AGENT_TOTAL_TIMEOUT_SECONDS)
        try:
            async with asyncio.timeout(max(.01, min(limit, 600 if file_generation else (180 if deep else 90)))):
                return await self._run(req, background_tasks, request_id)
        except TimeoutError:
            await self._record_failure(req, records, request_id, started, 'timeout')
            raise HTTPException(status_code=504, detail='Request deadline exceeded. Any completed external actions will not be replayed.')
        except Exception:
            await self._record_failure(req, records, request_id, started, 'error')
            raise
        finally:
            usage_records.reset(token)

    async def _record_failure(self, req, records, request_id, started, status):
        last = records[-1] if records else {}
        try:
            async with asyncio.timeout(2):
                await log_request_metric(req.guild_id, req.channel_id, req.user_id,
                    {"ollama":2,"kaggle":3}.get(last.get('provider'),1),
                    last.get('provider','unknown'),last.get('model','unknown'),
                    int((time.monotonic()-started)*1000),request_id=request_id,
                    provider_usage=records,status=status)
        except Exception:
            logger.warning('Failure metric unavailable request_id=%s status=%s',request_id,status)

    async def _run(self, req: Any, background_tasks: BackgroundTasks, request_id: str) -> Dict[str, Any]:
        """Execute chat completion request."""
        start_time = time.time()
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

        # Route Path: Bounded Agent Runtime (v4)
        runtime_enabled = ctx.agent_runtime_enabled if ctx.agent_runtime_enabled is not None else feature_enabled('agent',req.channel_id,req.guild_id)
        runtime_enabled = runtime_enabled and supports_native_tools(provider, model_name) and getattr(req, "file_generation", False) is not True
        evidence_urls = set()
        search_error = None
        incomplete = False
        configured_steps = settings.AGENT_DEEP_MAX_TOOL_STEPS if req.deep_search else settings.AGENT_MAX_TOOL_STEPS
        step_limit = max(0, min(configured_steps, 8))
        # Retrieval has one owner for every provider and both HTTP response modes.
        retrieval_requested = req.enable_web_search is not False and (
            ctx.enable_search or req.deep_search or req.search_query or
            (req.search_category and req.search_category != "all")
        )
        if retrieval_requested and step_limit == 0:
            search_error = "Request tool budget disables retrieval."
        if ctx.working_messages and retrieval_requested and step_limit > 0:
            target = next((m for m in reversed(ctx.working_messages) if m.get("role") == "user"), None)
            if target:
                query = req.search_query or target.get("content", "")
                match = re.search(r"following query:\s*[\"']([^\"']+)", query)
                if match:
                    query = match.group(1)
                data = await search_service.search_and_fetch(
                    query=query, max_results=5, fetch_top_n=5 if req.deep_search else 2,
                    category=req.search_category or "all",
                )
                search_calls += data.get("search_calls", 1)
                pages_fetched += data.get("pages_fetched", sum(bool(p.get("fetched", False)) for p in data.get("roamed_pages", [])))
                evidence_urls = {r["url"] for r in data.get("results", []) if r.get("url")}
                search_error = data.get("error")
                success = bool(data.get("context_text")) and not search_error
                tool_failures += int(not success)
                target["content"] += "\n\n" + fence_tool_data("web.research", data.get("context_text") or search_error or "No live evidence was found.")
                ctx.persona += "\nCite only URLs in the supplied evidence. Search snippets are not verified page content. If retrieval failed, state that live sources could not be verified."
                tool_trace.append({"tool": "web.search", "success": success, "duration_ms": int((time.time()-start_time)*1000)})
                tool_steps += 1
        elif ctx.working_messages and not retrieval_requested and not runtime_enabled and req.enable_web_search is not False:
            target = next((m for m in reversed(ctx.working_messages) if m.get("role") == "user"), None)
            if target:
                for url in web_search_engine.extract_urls(target.get("content", ""))[:min(2, step_limit)]:
                    result = await search_service.fetch(url, max_chars=5000)
                    pages_fetched += int(result.success)
                    tool_steps += 1
                    tool_failures += int(not result.success)
                    target["content"] += "\n\n" + fence_tool_data("web.fetch", result.content if result.success else "Page retrieval failed.")
                    tool_trace.append({"tool": "web.fetch", "success": result.success, "duration_ms": 0})
        remaining_steps = max(0, step_limit - tool_steps)
        if runtime_enabled:
            logger.debug("Executing request via v4 Bounded Agent Runtime.")
            selected_tools = self.capability_router.select_tools(
                messages=req.messages,
                provider=provider,
                model_name=model_name,
                enable_web_search=req.enable_web_search,
                deep_search=bool(req.deep_search),
                search_query=req.search_query,
                allow_code_exec=ctx.allow_code_exec,
                auto_code_test_mode=ctx.auto_code_test_mode,
                guild_id=req.guild_id,
            )
            mcp_enabled = ctx.mcp_enabled if ctx.mcp_enabled is not None else feature_enabled('mcp',req.channel_id,req.guild_id)
            selected_tools = [t for t in selected_tools if (t.source != 'mcp' or mcp_enabled) and not (retrieval_requested and t.name.startswith('web.'))]

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
                    max_steps=remaining_steps,
                )
                incomplete = run_res.incomplete
                raw_response_text = run_res.final_response
                tool_trace += run_res.tool_trace
                tool_steps += run_res.tool_steps
                search_calls += run_res.search_calls
                pages_fetched += run_res.pages_fetched
                sandbox_calls = run_res.sandbox_calls
                mcp_calls = run_res.mcp_calls
                tool_failures += run_res.tool_failures
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
                        messages=req.messages,
                        provider="gemini",
                        model_name="gemini-2.5-flash",
                        enable_web_search=req.enable_web_search,
                        deep_search=bool(req.deep_search),
                        search_query=req.search_query,
                        allow_code_exec=ctx.allow_code_exec,
                        auto_code_test_mode=ctx.auto_code_test_mode,
                        guild_id=req.guild_id,
                    )
                    gemini_tools = [t for t in gemini_tools if t.risk == 'read' and (t.source != 'mcp' or mcp_enabled) and not (retrieval_requested and t.name.startswith('web.'))]
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
                        max_steps=remaining_steps,
                    )
                    incomplete = run_res.incomplete
                    raw_response_text = run_res.final_response
                    tool_trace += run_res.tool_trace
                    tool_steps += run_res.tool_steps
                    search_calls += run_res.search_calls
                    pages_fetched += run_res.pages_fetched
                    sandbox_calls = run_res.sandbox_calls
                    mcp_calls = run_res.mcp_calls
                    tool_failures += run_res.tool_failures
                    input_tokens = run_res.input_tokens
                    output_tokens = run_res.output_tokens
                    agent_run_id = run_res.agent_run_id
                    agent_duration_ms = run_res.duration_ms
                else:
                    raise runtime_err

        # Route Path: Legacy v3 Generation (Backward Compatibility)
        else:
            logger.debug("Executing request via v3 Direct Generation path.")
            pass_enable_search = False

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

        if search_error:
            raw_response_text += "\n\nLive research unavailable; current sources could not be verified."

        if retrieval_requested:
            from backend.search.citations import validate_citations
            raw_response_text = validate_citations(raw_response_text, evidence_urls)

        # Extract generated files from response
        clean_response_text, extracted_files = extract_generated_files(raw_response_text)
        clean_response_text = sanitize_secrets(clean_response_text)
        for f in extracted_files:
            if isinstance(f, dict) and "content" in f and isinstance(f["content"], str):
                f["content"] = sanitize_secrets(f["content"])

        from backend.memory.usage import usage_records
        records = usage_records.get() or []
        if records:
            input_tokens = sum(r['input_tokens'] or 0 for r in records) if all(r['input_tokens'] is not None for r in records) else None
            output_tokens = sum(r['output_tokens'] or 0 for r in records) if all(r['output_tokens'] is not None for r in records) else None
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            f"request_id={request_id} provider={provider} model={model_name} status=ok duration={duration_ms}ms"
        )
        background_tasks.add_task(
            log_request_metric,
            guild_id=req.guild_id,
            channel_id=req.channel_id,
            user_id=req.user_id,
            tier={"ollama": 2, "kaggle": 3}.get(provider, 1),
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
            provider_usage=records,
            status="partial" if incomplete else "ok",
        )

        if req.user_id:
            background_tasks.add_task(
                extract_and_store_user_memories,
                user_id=req.user_id,
                messages=req.messages + [{"role": "assistant", "content": clean_response_text}],
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
            "incomplete": incomplete,
            "research_error": search_error,
        }

        # Include tool metadata when running in agent mode
        if runtime_enabled or tool_steps > 0:
            resp_payload["tool_trace"] = tool_trace
            resp_payload["tool_steps"] = tool_steps

        return resp_payload


chat_orchestrator = ChatOrchestrator()
