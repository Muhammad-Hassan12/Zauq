import asyncio
import time
from fastapi import APIRouter, HTTPException

from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from backend.memory.db import db_helper
from backend.models.router import model_router
from backend.memory.episodic import extract_and_store_user_memories

router = APIRouter(prefix="/api/chat", tags=["Chat Engine"])

class AttachmentItem(BaseModel):
    filename: str
    content_type: Optional[str] = ""
    bytes_b64: Optional[str] = None

class ChatRequest(BaseModel):
    channel_id: str
    guild_id: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    messages: List[Dict[str, str]]
    mode_override: Optional[str] = None
    attachments: Optional[List[AttachmentItem]] = None


class ChannelProfileRequest(BaseModel):
    channel_id: str
    guild_id: str
    operating_mode: str
    temperature: Optional[float] = None
    allow_code_exec: Optional[bool] = None

@router.post("/profile")
async def update_channel_profile(req: ChannelProfileRequest):
    try:
        temp = req.temperature if req.temperature is not None else (0.2 if req.operating_mode == "dev" else 0.75)
        allow_exec = req.allow_code_exec if req.allow_code_exec is not None else (req.operating_mode == "dev")
        res = await db_helper.upsert_channel_profile(
            channel_id=req.channel_id,
            guild_id=req.guild_id,
            operating_mode=req.operating_mode,
            temperature=temp,
            allow_code_exec=allow_exec
        )
        return {"status": "success", "data": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


DEV_PERSONA_SEED = (
    "You are Zauq operating in Dev Mode. You are a senior software engineer and architect. "
    "Be concise, highly technical, and precise. Provide code snippets using proper syntax highlighting. "
    "Avoid unnecessary conversational filler."
)

HANGOUT_PERSONA_SEED = (
    "You are Zauq operating in Hangout Mode. You are an expressive, witty, and engaging server companion. "
    "Match the casual energy of the community while staying helpful, funny, and friendly."
)

async def _build_chat_context(req: ChatRequest) -> tuple[str, str, float, str, str]:
    # 1. Fetch channel profile / guild config
    channel_profile = await db_helper.get_channel_profile(req.channel_id)
    guild_config = await db_helper.get_guild_config(req.guild_id) if req.guild_id else None

    # Determine mode
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
    if req.guild_id and req.messages:
        from backend.memory.rag import get_lore_context_prompt
        last_user_query = req.messages[-1].get("content", "")
        lore_prompt = await get_lore_context_prompt(req.guild_id, last_user_query)
        if lore_prompt:
            persona += lore_prompt

    # 4. Determine Model Selection
    model_sel = await db_helper.get_model_selection(req.channel_id)
    if model_sel:
        provider = model_sel.get("provider", "gemini")
        model_name = model_sel.get("model_name", "gemini-2.5-flash")
    else:
        provider = "gemini"
        model_name = "gemini-2.5-flash"

    # 5. Enforce strict output guard (prevents Gemma/Open model CoT scratchpad leaks)
    persona += (
        "\n\n[CRITICAL OUTPUT DIRECTIVE]: "
        "Speak DIRECTLY to the user as Zauq. Never output internal thoughts, analysis, draft options, "
        "reasoning steps, or scratchpad bullet points. Output ONLY your final spoken reply."
    )

    return persona, mode, temp, provider, model_name


import base64
from backend.parsers.file_parser import parse_attachment
from backend.memory.metrics import log_request_metric

@router.post("")
async def chat_completion(req: ChatRequest):
    start_time = time.time()
    persona, mode, temp, provider, model_name = await _build_chat_context(req)

    # Process attached files / images
    image_parts = []
    if req.attachments and req.messages:
        attached_text_blocks = []
        for att in req.attachments:
            if att.bytes_b64:
                try:
                    raw_bytes = base64.b64decode(att.bytes_b64)
                    parsed = parse_attachment(raw_bytes, att.filename, att.content_type or "")
                    if parsed["type"] == "image":
                        image_parts.append(parsed)
                    else:
                        attached_text_blocks.append(f"\n\n[Attached Document: {att.filename}]\n{parsed['content']}")
                except Exception as parse_err:
                    print(f"[Attachment Warning] Failed to parse attachment {att.filename}: {parse_err}")
        
        if attached_text_blocks:
            # Guarantee text attachments append to the last 'user' role message
            target_user_msg = next((m for m in reversed(req.messages) if m.get("role") == "user"), req.messages[-1])
            target_user_msg["content"] += "".join(attached_text_blocks)

    try:
        response_text = await model_router.generate(
            messages=req.messages,
            provider=provider,
            model_name=model_name,
            system_prompt=persona,
            temperature=temp,
            image_parts=image_parts
        )

        duration_ms = int((time.time() - start_time) * 1000)
        asyncio.create_task(
            log_request_metric(req.guild_id, req.channel_id, req.user_id, 1, provider, model_name, duration_ms)
        )

        # Trigger background episodic memory extraction
        if req.user_id:
            asyncio.create_task(
                extract_and_store_user_memories(
                    user_id=req.user_id,
                    messages=req.messages + [{"role": "assistant", "content": response_text}],
                    provider=provider,
                    model_name=model_name
                )
            )

        return {
            "mode": mode,
            "provider": provider,
            "model": model_name,
            "response": response_text
        }
    except Exception as e:
        err_detail = str(e) or repr(e) or "An unexpected model engine error occurred."
        raise HTTPException(status_code=500, detail=err_detail)


@router.post("/stream")
async def chat_completion_stream(req: ChatRequest):
    start_time = time.time()
    persona, mode, temp, provider, model_name = await _build_chat_context(req)

    async def event_generator():
        collected_chunks = []
        try:
            async for chunk in model_router.generate_stream(
                messages=req.messages,
                provider=provider,
                model_name=model_name,
                system_prompt=persona,
                temperature=temp
            ):
                collected_chunks.append(chunk)
                yield chunk
            
            duration_ms = int((time.time() - start_time) * 1000)
            asyncio.create_task(
                log_request_metric(req.guild_id, req.channel_id, req.user_id, 1, provider, model_name, duration_ms)
            )

            # Background extraction post-stream
            full_response = "".join(collected_chunks)
            if req.user_id and full_response:
                asyncio.create_task(
                    extract_and_store_user_memories(
                        user_id=req.user_id,
                        messages=req.messages + [{"role": "assistant", "content": full_response}],
                        provider=provider,
                        model_name=model_name
                    )
                )

        except Exception as e:
            yield f"\n[Error: {str(e)}]"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

