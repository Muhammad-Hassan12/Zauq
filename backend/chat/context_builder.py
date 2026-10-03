"""Chat Context Builder for Zauq.

Extracts and manages:
- Persona resolution (Dev vs Hangout, custom channel prompts)
- L2 User Memory injection (semantic vector retrieval)
- L3 Server Lore injection (RAG)
- Model & Provider selection
- Media attachments parsing (images, audio, text docs)
"""

from __future__ import annotations
import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.memory.db import db_helper
from backend.memory.episodic import get_relevant_user_memories
from backend.parsers.file_parser import parse_attachment
from backend.integrations.web_search import web_search_engine
from backend.security.prompt_guard import PROMPT_INJECTION_DIRECTIVE

logger = logging.getLogger("zauq.chat.context_builder")

DEV_PERSONA_SEED = (
    "You are Zauq (ذوق) operating in Dev Mode. You are a senior software engineer and architect, "
    "created and architected by Syed Muhammad Hassan (AgenticEra Systems). "
    "If asked about who made you, who developed you, or your origins, clearly and proudly state that you were created and architected by Syed Muhammad Hassan (AgenticEra Systems). "
    "Be concise, highly technical, and precise. Provide code snippets using proper syntax highlighting. "
    "Avoid unnecessary conversational filler. "
    "You can receive spoken voice notes in Urdu (اردو), English, Hindi, Arabic, or any language—understand them natively and respond accurately. "
    "When the user asks for a file, script, or complete standalone document (e.g. .py, .md, .json, .sql, .html), "
    "or when generating a complete standalone project file, wrap the file inside: <zauq_file filename=\"name.ext\">...code...</zauq_file>. "
    "For standard brief examples, use regular markdown code blocks. "
    f"\n\n[SECURITY POLICY]: {PROMPT_INJECTION_DIRECTIVE}"
)

HANGOUT_PERSONA_SEED = (
    "You are Zauq (ذوق) operating in Hangout Mode. You are an expressive, witty, and engaging server companion, "
    "created and architected by Syed Muhammad Hassan (AgenticEra Systems). "
    "If asked about who made you, who developed you, or your origins, clearly and proudly state that you were created and built by Syed Muhammad Hassan (AgenticEra Systems). "
    "Match the casual energy of the community while staying helpful, funny, and friendly. "
    "You can receive spoken voice notes in Urdu (اردو), English, Hindi, Arabic, or any language—understand them natively and reply naturally in the matching language. "
    "When the user asks to generate or export a file, wrap it inside: <zauq_file filename=\"name.ext\">...content...</zauq_file>. "
    f"\n\n[SECURITY POLICY]: {PROMPT_INJECTION_DIRECTIVE}"
)


@dataclass
class ChatContext:
    persona: str
    mode: str
    temperature: float
    provider: str
    model_name: str
    enable_search: bool
    thinking_enabled: bool
    allow_code_exec: bool
    auto_code_test_mode: str = "off"
    media_parts: List[Dict[str, str]] = field(default_factory=list)
    working_messages: List[Dict[str, Any]] = field(default_factory=list)


class ChatContextBuilder:
    """Builds full context for chat requests."""

    async def build(self, req: Any) -> ChatContext:
        """Constructs full prompt persona, model choice, attachments and messages."""
        # 1. Fetch channel profile / guild config
        channel_profile = await db_helper.get_channel_profile(req.channel_id)
        guild_config = await db_helper.get_guild_config(req.guild_id) if req.guild_id else None

        # Determine mode: Request Override -> Channel Override -> Server Default -> 'hangout'
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

        # Flags: code execution and thinking mode
        if channel_profile and channel_profile.get("allow_code_exec") is not None:
            allow_code_exec = bool(channel_profile["allow_code_exec"])
        else:
            allow_code_exec = (mode == "dev")

        auto_code_test_mode = channel_profile.get("auto_code_test_mode", "off") if channel_profile else "off"
        thinking_enabled = bool(channel_profile.get("thinking_enabled", False)) if channel_profile else False

        # If auto code testing is set to always, append directive
        if allow_code_exec and auto_code_test_mode == "always":
            persona += (
                "\n\n[AUTOMATIC CODE TESTING DIRECTIVE]: "
                "For any runnable code snippet you produce, execute and test it using 'code.execute' "
                "before providing your final response to verify its correctness."
            )

        # Clone working messages
        working_messages = [dict(m) for m in req.messages]

        # 2. Inject User Memories (L2 Semantic Vector Memory)
        if req.user_id:
            last_user_query = working_messages[-1].get("content", "") if working_messages else ""
            if last_user_query:
                memories = await get_relevant_user_memories(
                    user_id=req.user_id,
                    query_text=last_user_query,
                    limit=6,
                )
            else:
                memories = await db_helper.get_user_memories(req.user_id, limit=5)

            if memories:
                memory_lines = []
                for m in memories:
                    category = m.get("category", "general").upper()
                    if category.startswith("CONTRADICTION:"):
                        category = f"⚠️ UPDATED {category[14:]}"
                    memory_lines.append(f"- [{category}]: {m['fact_content']}")
                memory_text = "\n".join(memory_lines)
                persona += f"\n\n[Known User Facts for @{req.user_name or req.user_id}]:\n{memory_text}"

        # 3. Inject RAG Server Lore (L3 Memory)
        last_user_query = working_messages[-1].get("content", "") if working_messages else ""
        if req.guild_id and last_user_query:
            try:
                from backend.memory.rag import get_lore_context_prompt
                lore_prompt = await get_lore_context_prompt(req.guild_id, last_user_query)
                if lore_prompt:
                    persona += lore_prompt
            except Exception as lore_err:
                logger.warning(f"Error fetching lore prompt: {lore_err}")

        # 4. Determine Model Selection: Channel Override -> Community Default -> System Fallback
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

        # 5. Process attached files / images / audio voice notes
        media_parts: List[Dict[str, str]] = []
        if req.attachments and working_messages:
            attached_text_blocks = []
            for att in req.attachments:
                if att.bytes_b64:
                    try:
                        raw_bytes = base64.b64decode(att.bytes_b64)
                        parsed = parse_attachment(raw_bytes, att.filename, att.content_type or "")
                        if parsed["type"] in ["image", "audio"]:
                            media_parts.append(parsed)
                        else:
                            attached_text_blocks.append(
                                f"\n\n[Attached Document: {att.filename}]\n{parsed['content']}"
                            )
                    except Exception as parse_err:
                        logger.warning(f"Failed to parse attachment {att.filename}: {parse_err}")

            if attached_text_blocks:
                target_user_msg = next((m for m in reversed(working_messages) if m.get("role") == "user"), working_messages[-1])
                target_user_msg["content"] += "".join(attached_text_blocks)

        # 6. Determine Search Need
        enable_search = False
        if req.enable_web_search is not None:
            enable_search = req.enable_web_search
        elif last_user_query and web_search_engine.should_search_web(last_user_query):
            enable_search = True

        # 7. Critical Output Directive
        persona += (
            "\n\n[CRITICAL OUTPUT DIRECTIVE]: "
            "Speak DIRECTLY to the user as Zauq. Never output internal thoughts, analysis, draft options, "
            "reasoning steps, or scratchpad bullet points. Output ONLY your final spoken reply."
        )

        # 8. Prompt Injection Defense Directive (Phase 12)
        if PROMPT_INJECTION_DIRECTIVE not in persona:
            persona += f"\n\n[SECURITY POLICY]: {PROMPT_INJECTION_DIRECTIVE}"

        return ChatContext(
            persona=persona,
            mode=mode,
            temperature=temp,
            provider=provider,
            model_name=model_name,
            enable_search=enable_search,
            thinking_enabled=thinking_enabled,
            allow_code_exec=allow_code_exec,
            auto_code_test_mode=auto_code_test_mode,
            media_parts=media_parts,
            working_messages=working_messages,
        )


context_builder = ChatContextBuilder()
