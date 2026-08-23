import time
import base64
import asyncio
import logging
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from typing import List, Dict, Optional, Any, Literal

from backend.config import settings
from backend.memory.db import db_helper
from backend.models.router import model_router
from backend.memory.episodic import extract_and_store_user_memories
from backend.parsers.file_parser import parse_attachment, extract_generated_files
from backend.integrations.web_search import web_search_engine
from backend.memory.metrics import log_request_metric

logger = logging.getLogger("zauq.chat")

router = APIRouter(prefix="/api/chat", tags=["Chat Engine"])

class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str

class AttachmentItem(BaseModel):
    filename: str
    content_type: Optional[str] = ""
    bytes_b64: Optional[str] = None

class ChatRequest(BaseModel):
    channel_id: str
    guild_id: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    messages: List[Dict[str, Any]]
    mode_override: Optional[str] = None
    attachments: Optional[List[AttachmentItem]] = None
    enable_web_search: Optional[bool] = None
    deep_search: Optional[bool] = False
    search_category: Optional[str] = "all"
    search_query: Optional[str] = None

    @field_validator('messages')
    @classmethod
    def _validate_messages(cls, v):
        """Validate message dicts: required fields, valid roles, size limits."""
        valid_roles = {"user", "assistant", "system"}
        if len(v) > 50:
            raise ValueError("Too many messages in request. Maximum is 50.")
        for i, msg in enumerate(v):
            if "role" not in msg or "content" not in msg:
                raise ValueError(f"Message at index {i} must have 'role' and 'content' keys")
            if msg["role"] not in valid_roles:
                raise ValueError(f"Message at index {i} has invalid role '{msg['role']}'. Must be one of: {valid_roles}")
            if isinstance(msg["content"], str) and len(msg["content"]) > 15000:
                raise ValueError(f"Message at index {i} content exceeds maximum length of 15,000 characters.")
        return v

    @field_validator('attachments')
    @classmethod
    def _validate_attachments(cls, v):
        """Limit attachment count and individual size."""
        if v is None:
            return v
        if len(v) > 4:
            raise ValueError("Too many attachments. Maximum is 4 per request.")
        return v

class ChannelProfileRequest(BaseModel):
    channel_id: Optional[str] = None
    guild_id: Optional[str] = None
    scope: Optional[str] = "channel"  # 'channel' or 'server'
    operating_mode: str
    temperature: Optional[float] = None
    allow_code_exec: Optional[bool] = None

@router.post("/profile")
async def update_channel_profile(req: ChannelProfileRequest):
    try:
        temp = req.temperature if req.temperature is not None else (0.2 if req.operating_mode == "dev" else 0.75)
        allow_exec = req.allow_code_exec if req.allow_code_exec is not None else (req.operating_mode == "dev")
        scope = (req.scope or "channel").lower()

        if scope in ["server", "community", "guild"] and req.guild_id and req.guild_id != "dm":
            res = await db_helper.upsert_guild_config(
                guild_id=req.guild_id,
                default_mode=req.operating_mode
            )
            return {"status": "success", "scope": "server", "data": res}
        else:
            if not req.channel_id:
                raise HTTPException(status_code=400, detail="channel_id is required for channel-scoped configuration.")
            res = await db_helper.upsert_channel_profile(
                channel_id=req.channel_id,
                guild_id=req.guild_id or "dm",
                operating_mode=req.operating_mode,
                temperature=temp,
                allow_code_exec=allow_exec
            )
            return {"status": "success", "scope": "channel", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/profile/reset")
async def reset_channel_profile(channel_id: str):
    """Deletes a channel mode override so the channel inherits the community server default mode."""
    success = await db_helper.delete_channel_profile(channel_id)
    return {
        "status": "success",
        "channel_id": channel_id,
        "cleared": success,
        "detail": "Channel mode override cleared. Channel will now inherit the community server default mode."
    }

DEV_PERSONA_SEED = (
    "You are Zauq (ذوق) operating in Dev Mode. You are a senior software engineer and architect, "
    "created and architected by Syed Muhammad Hassan (AgenticEra Systems). "
    "If asked about who made you, who developed you, or your origins, clearly and proudly state that you were created and architected by Syed Muhammad Hassan (AgenticEra Systems). "
    "Be concise, highly technical, and precise. Provide code snippets using proper syntax highlighting. "
    "Avoid unnecessary conversational filler. "
    "You can receive spoken voice notes in Urdu (اردو), English, Hindi, Arabic, or any language—understand them natively and respond accurately. "
    "When the user asks for a file, script, or complete standalone document (e.g. .py, .md, .json, .sql, .html), "
    "or when generating a complete standalone project file, wrap the file inside: <zauq_file filename=\"name.ext\">...code...</zauq_file>. "
    "For standard brief examples, use regular markdown code blocks."
)

HANGOUT_PERSONA_SEED = (
    "You are Zauq (ذوق) operating in Hangout Mode. You are an expressive, witty, and engaging server companion, "
    "created and architected by Syed Muhammad Hassan (AgenticEra Systems). "
    "If asked about who made you, who developed you, or your origins, clearly and proudly state that you were created and built by Syed Muhammad Hassan (AgenticEra Systems). "
    "Match the casual energy of the community while staying helpful, funny, and friendly. "
    "You can receive spoken voice notes in Urdu (اردو), English, Hindi, Arabic, or any language—understand them natively and reply naturally in the matching language. "
    "When the user asks to generate or export a file, wrap it inside: <zauq_file filename=\"name.ext\">...content...</zauq_file>."
)

async def _build_chat_context(req: ChatRequest) -> tuple[str, str, float, str, str, bool]:
    # 1. Fetch channel profile / guild config
    channel_profile = await db_helper.get_channel_profile(req.channel_id)
    guild_config = await db_helper.get_guild_config(req.guild_id) if req.guild_id else None

    # Determine mode: Channel Override -> Server Default -> System Default ('hangout')
    mode = req.mode_override
    if not mode and channel_profile:
        mode = channel_profile.get("operating_mode")
    if not mode and guild_config:
        mode = guild_config.get("default_mode")
    if not mode:
        mode = "hangout"

    # Base persona
    if channel_profile and channel_profile.get("system_persona_prompt"):
        persona = channel_profile["system_persona_prompt"]
    else:
        persona = DEV_PERSONA_SEED if mode == "dev" else HANGOUT_PERSONA_SEED

    # Temperature
    if channel_profile and channel_profile.get("temperature") is not None:
        temp = float(channel_profile["temperature"])
    else:
        temp = 0.2 if mode == "dev" else 0.75

    # 2. Inject User Memories (L2 Memory)
    if req.user_id:
        memories = await db_helper.get_user_memories(req.user_id, limit=5)
        if memories:
            memory_text = "\n".join([f"- {m['fact_content']}" for m in memories])
            persona += f"\n\n[Known User Facts for @{req.user_name or req.user_id}]:\n{memory_text}"

    # 3. Inject RAG Server Lore (L3 Memory)
    last_user_query = req.messages[-1].get("content", "") if req.messages else ""
    if req.guild_id and last_user_query:
        from backend.memory.rag import get_lore_context_prompt
        lore_prompt = await get_lore_context_prompt(req.guild_id, last_user_query)
        if lore_prompt:
            persona += lore_prompt

    # 4. Determine Model Selection: Channel Override -> Community Default -> System Fallback (Gemini 2.5 Flash)
    model_sel = await db_helper.get_model_selection(req.channel_id)
    if model_sel and model_sel.get("provider"):
        provider = model_sel.get("provider", "gemini")
        model_name = model_sel.get("model_name", "gemini-2.5-flash")
    elif guild_config and guild_config.get("default_provider"):
        provider = guild_config.get("default_provider", "gemini")
        model_name = guild_config.get("default_model_name", "gemini-2.5-flash")
    else:
        provider = "gemini"
        model_name = "gemini-2.5-flash"

    # 5. Determine Search Need
    enable_search = False
    if req.enable_web_search is not None:
        enable_search = req.enable_web_search
    elif last_user_query and web_search_engine.should_search_web(last_user_query):
        enable_search = True

    # 6. Enforce strict output guard
    persona += (
        "\n\n[CRITICAL OUTPUT DIRECTIVE]: "
        "Speak DIRECTLY to the user as Zauq. Never output internal thoughts, analysis, draft options, "
        "reasoning steps, or scratchpad bullet points. Output ONLY your final spoken reply."
    )

    return persona, mode, temp, provider, model_name, enable_search

@router.post("")
async def chat_completion(req: ChatRequest, background_tasks: BackgroundTasks):
    start_time = time.time()
    persona, mode, temp, provider, model_name, enable_search = await _build_chat_context(req)

    # Process attached files / images / audio voice notes
    media_parts = []
    if req.attachments and req.messages:
        attached_text_blocks = []
        for att in req.attachments:
            if att.bytes_b64:
                try:
                    raw_bytes = base64.b64decode(att.bytes_b64)
                    parsed = parse_attachment(raw_bytes, att.filename, att.content_type or "")
                    if parsed["type"] in ["image", "audio"]:
                        media_parts.append(parsed)
                    else:
                        attached_text_blocks.append(f"\n\n[Attached Document: {att.filename}]\n{parsed['content']}")
                except Exception as parse_err:
                    logger.warning(f"Failed to parse attachment {att.filename}: {parse_err}")
        
        if attached_text_blocks:
            target_user_msg = next((m for m in reversed(req.messages) if m.get("role") == "user"), req.messages[-1])
            target_user_msg["content"] += "".join(attached_text_blocks)

    # Detect live URLs in user message and scrape webpage content
    if req.messages:
        target_user_msg = next((m for m in reversed(req.messages) if m.get("role") == "user"), req.messages[-1])
        urls = web_search_engine.extract_urls(target_user_msg.get("content", ""))
        for u in urls[:2]:  # Limit to first 2 URLs
            try:
                page_text = await web_search_engine.fetch_url_content(u, max_chars=5000)
                if page_text and not page_text.startswith("[Failed"):
                    target_user_msg["content"] += f"\n\n[Attached Live Webpage Content for {u}]:\n{page_text}"
            except Exception as url_err:
                logger.info(f"URL scrape failed for {u}: {url_err}")

    # If web search or deep search is requested, enrich context with Deep Web Roaming
    if req.messages and (req.deep_search or req.enable_web_search or (req.search_category and req.search_category != "all")):
        target_user_msg = next((m for m in reversed(req.messages) if m.get("role") == "user"), req.messages[-1])
        user_text = target_user_msg.get("content", "")
        
        # Extract the pure search query
        raw_search_q = req.search_query or user_text
        if 'following query: "' in raw_search_q:
            match = re.search(r'following query:\s*"([^"]+)"', raw_search_q)
            if match:
                raw_search_q = match.group(1)
        elif 'following query: \'' in raw_search_q:
            match = re.search(r"following query:\s*'([^']+)'", raw_search_q)
            if match:
                raw_search_q = match.group(1)

        search_data = await web_search_engine.deep_search_and_roam(
            query=raw_search_q,
            max_results=5,
            roam_top_n=3 if req.deep_search else 2,
            category=req.search_category or "all"
        )
        if search_data.get("context_text"):
            target_user_msg["content"] += (
                f"\n\n[Autonomous Deep Web Research Context & Live Sources]:\n"
                f"{search_data['context_text']}\n\n"
                "Synthesize a well-structured, authoritative, and comprehensive answer strictly utilizing the live research sources provided above. Include relevant markdown citations."
            )

    try:
        try:
            raw_response_text = await model_router.generate(
                messages=req.messages,
                provider=provider,
                model_name=model_name,
                system_prompt=persona,
                temperature=temp,
                media_parts=media_parts,
                enable_search=enable_search
            )
        except Exception as prov_err:
            # If a secondary provider fails (e.g. mismatched model name, offline Ollama/Kaggle),
            # gracefully fall back to primary Gemini 2.5 Flash to guarantee zero user interruption
            if provider != "gemini" and settings.GEMINI_API_KEY:
                logger.warning(f"Provider '{provider}' with model '{model_name}' failed ({prov_err}). Gracefully falling back to Gemini 2.5 Flash.")
                provider = "gemini"
                model_name = "gemini-2.5-flash"
                raw_response_text = await model_router.generate(
                    messages=req.messages,
                    provider="gemini",
                    model_name="gemini-2.5-flash",
                    system_prompt=persona,
                    temperature=temp,
                    media_parts=media_parts,
                    enable_search=enable_search
                )
            else:
                raise prov_err

        # Extract any generated files from model output (<zauq_file> tags or annotated code blocks)
        clean_response_text, extracted_files = extract_generated_files(raw_response_text)

        duration_ms = int((time.time() - start_time) * 1000)
        background_tasks.add_task(
            log_request_metric, req.guild_id, req.channel_id, req.user_id, 1, provider, model_name, duration_ms
        )

        if req.user_id:
            background_tasks.add_task(
                extract_and_store_user_memories,
                user_id=req.user_id,
                messages=req.messages + [{"role": "assistant", "content": clean_response_text}],
                provider=provider,
                model_name=model_name
            )

        return {
            "mode": mode,
            "provider": provider,
            "model": model_name,
            "response": clean_response_text,
            "files": extracted_files
        }
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred. Please try again.")

@router.post("/stream")
async def chat_completion_stream(req: ChatRequest):
    start_time = time.time()
    persona, mode, temp, provider, model_name, enable_search = await _build_chat_context(req)

    media_parts = []
    if req.attachments:
        for att in req.attachments:
            if att.bytes_b64:
                try:
                    raw_bytes = base64.b64decode(att.bytes_b64)
                    parsed = parse_attachment(raw_bytes, att.filename, att.content_type or "")
                    if parsed["type"] in ["image", "audio"]:
                        media_parts.append(parsed)
                except Exception:
                    pass

    async def event_generator():
        collected_chunks = []
        try:
            async for chunk in model_router.generate_stream(
                messages=req.messages,
                provider=provider,
                model_name=model_name,
                system_prompt=persona,
                temperature=temp,
                media_parts=media_parts,
                enable_search=enable_search
            ):
                collected_chunks.append(chunk)
                yield chunk
            
            duration_ms = int((time.time() - start_time) * 1000)
            asyncio.create_task(
                log_request_metric(req.guild_id, req.channel_id, req.user_id, 1, provider, model_name, duration_ms)
            )

            full_response = "".join(collected_chunks)
            clean_text, _ = extract_generated_files(full_response)
            if req.user_id and clean_text:
                asyncio.create_task(
                    extract_and_store_user_memories(
                        user_id=req.user_id,
                        messages=req.messages + [{"role": "assistant", "content": clean_text}],
                        provider=provider,
                        model_name=model_name
                    )
                )

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield f"\n[Error: {str(e)}]"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
