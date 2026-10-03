import re
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
from backend.memory.episodic import extract_and_store_user_memories, get_relevant_user_memories
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
    thinking_enabled: Optional[bool] = None

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
            # Preserve existing thinking_enabled unless explicitly set
            existing_profile = await db_helper.get_channel_profile(req.channel_id) or {}
            thinking = req.thinking_enabled if req.thinking_enabled is not None else existing_profile.get("thinking_enabled", False)
            res = await db_helper.upsert_channel_profile(
                channel_id=req.channel_id,
                guild_id=req.guild_id or "dm",
                operating_mode=req.operating_mode,
                temperature=temp,
                allow_code_exec=allow_exec,
                thinking_enabled=thinking
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

class ThinkingToggleRequest(BaseModel):
    channel_id: str
    guild_id: Optional[str] = None
    thinking_enabled: bool

@router.post("/thinking")
async def toggle_thinking_mode(req: ThinkingToggleRequest):
    """
    Toggle Gemini thinking/reasoning mode for a specific channel.
    Preserves all existing channel profile settings (mode, temperature, etc.).
    """
    try:
        res = await db_helper.set_channel_thinking(
            channel_id=req.channel_id,
            guild_id=req.guild_id or "dm",
            enabled=req.thinking_enabled
        )
        return {
            "status": "success",
            "channel_id": req.channel_id,
            "thinking_enabled": req.thinking_enabled,
            "data": res
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

from backend.chat.context_builder import context_builder, DEV_PERSONA_SEED, HANGOUT_PERSONA_SEED
from backend.chat.orchestrator import chat_orchestrator

async def _build_chat_context(req: ChatRequest) -> tuple[str, str, float, str, str, bool, bool]:
    """
    Returns: (persona, mode, temp, provider, model_name, enable_search, thinking_enabled)
    Delegates to context_builder for backward compatibility.
    """
    ctx = await context_builder.build(req)
    return (
        ctx.persona,
        ctx.mode,
        ctx.temperature,
        ctx.provider,
        ctx.model_name,
        ctx.enable_search,
        ctx.thinking_enabled,
    )

@router.post("")
async def chat_completion(req: ChatRequest, background_tasks: BackgroundTasks):
    try:
        return await chat_orchestrator.run(req, background_tasks)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred. Please try again.")


@router.post("/stream")
async def chat_completion_stream(req: ChatRequest):
    start_time = time.time()
    persona, mode, temp, provider, model_name, enable_search, thinking_enabled = await _build_chat_context(req)

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
                enable_search=enable_search,
                thinking_enabled=thinking_enabled
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
