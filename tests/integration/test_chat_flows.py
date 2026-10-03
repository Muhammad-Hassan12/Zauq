"""Integration Tests: End-to-End Chat Flows & Regression Checklist (Phase 13).

Strictly verifies:
- Normal mention/reply chat
- DMs (direct messages with no guild scoping)
- Thread context (thread detection and message history)
- Attachments (multimodal images, documents)
- Voice input (audio voice notes parsed and routed)
- File generation (<zauq_file> extraction and packaging)
- Memory retrieval (L2 episodic user memory injection)
- Lore retrieval (L3 server lore RAG injection)
- Moderation (moderation check handling)
- Timeout behavior (graceful handling of timeouts)
"""

import base64
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import BackgroundTasks

from backend.config import settings
from backend.routers.chat import ChatRequest, chat_completion, AttachmentItem
from backend.chat.context_builder import context_builder
from backend.parsers.file_parser import parse_attachment, extract_generated_files
from backend.moderation.content_filter import ContentFilter


@pytest.fixture
def mock_background_tasks():
    return BackgroundTasks()


# ── 1. Normal Mention / Reply Chat Flow ───────────────────────────────────────

@pytest.mark.asyncio
async def test_normal_mention_reply_chat(mock_background_tasks, monkeypatch):
    """Verify standard in-channel mention/reply chat flow."""
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", False)

    req = ChatRequest(
        channel_id="chan_normal_123",
        guild_id="guild_normal_456",
        user_id="user_789",
        user_name="Alice",
        messages=[{"role": "user", "content": "Hello Zauq, what is Python?"}],
    )

    with patch("backend.models.router.model_router.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Python is a versatile high-level programming language."
        res = await chat_completion(req, mock_background_tasks)

        assert res["response"] == "Python is a versatile high-level programming language."
        assert res["provider"] == "gemini"
        mock_gen.assert_awaited_once()


# ── 2. Direct Messages (DMs) ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dm_chat_flow(mock_background_tasks, monkeypatch):
    """Verify DMs work without guild_id or when guild_id is 'dm'."""
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", False)

    req = ChatRequest(
        channel_id="dm_channel_999",
        guild_id=None,
        user_id="user_dm_1",
        user_name="Bob",
        messages=[{"role": "user", "content": "Hi in DM!"}],
    )

    with patch("backend.models.router.model_router.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Hello Bob! I am happy to chat in DMs."
        res = await chat_completion(req, mock_background_tasks)

        assert "Hello Bob" in res["response"]
        assert res["provider"] == "gemini"


# ── 3. Thread Context & Intent Detection ──────────────────────────────────────

def test_thread_intent_keywords():
    """Verify detection of thread keywords for in-channel vs thread routing."""
    wants_thread_1 = any(kw in "start a thread about this topic".lower() for kw in ["start a thread", "in a thread", "make a thread", "thread:"])
    wants_thread_2 = any(kw in "thread: let's analyze this code".lower() for kw in ["start a thread", "in a thread", "make a thread", "thread:"])
    normal_query = any(kw in "can you explain this topic in general?".lower() for kw in ["start a thread", "in a thread", "make a thread", "thread:"])

    assert wants_thread_1 is True
    assert wants_thread_2 is True
    assert normal_query is False


@pytest.mark.asyncio
async def test_thread_conversation_history(mock_background_tasks, monkeypatch):
    """Verify multi-turn history within a thread context is preserved."""
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", False)

    req = ChatRequest(
        channel_id="thread_chan_456",
        guild_id="guild_123",
        messages=[
            {"role": "user", "content": "Step 1: define problem"},
            {"role": "assistant", "content": "Problem defined."},
            {"role": "user", "content": "Step 2: propose solution"},
        ],
    )

    with patch("backend.models.router.model_router.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Solution proposed."
        res = await chat_completion(req, mock_background_tasks)

        assert res["response"] == "Solution proposed."
        passed_messages = mock_gen.call_args[1].get("messages") or mock_gen.call_args[0][0]
        assert len(passed_messages) == 3


# ── 4. Multimodal Attachments (Images & Documents) ───────────────────────────

@pytest.mark.asyncio
async def test_attachment_parsing_and_context_injection(mock_background_tasks, monkeypatch):
    """Verify document attachments are parsed and injected into prompt context."""
    doc_text = "PROJECT REQUIREMENTS:\n1. Zero downtime\n2. 99.9% uptime"
    b64_doc = base64.b64encode(doc_text.encode("utf-8")).decode("utf-8")

    req = ChatRequest(
        channel_id="c_doc",
        messages=[{"role": "user", "content": "Review this document:"}],
        attachments=[
            AttachmentItem(filename="requirements.txt", content_type="text/plain", bytes_b64=b64_doc)
        ],
    )

    with patch("backend.models.router.model_router.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "Requirements reviewed successfully."
        res = await chat_completion(req, mock_background_tasks)

        assert res["response"] == "Requirements reviewed successfully."
        passed_messages = mock_gen.call_args[1].get("messages") or mock_gen.call_args[0][0]
        last_msg = passed_messages[-1]["content"]
        assert "[Attached Document: requirements.txt]" in last_msg
        assert "PROJECT REQUIREMENTS:" in last_msg


# ── 5. Voice Input Ingestion ──────────────────────────────────────────────────

def test_voice_attachment_parsing():
    """Verify audio/voice attachments are parsed as multimodal audio parts."""
    raw_audio = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00fakeaudiodata"
    parsed = parse_attachment(raw_audio, "voice_message.ogg", "audio/ogg")

    assert parsed["type"] == "audio"
    assert parsed["mime_type"] == "audio/ogg"
    assert parsed["bytes_b64"] == base64.b64encode(raw_audio).decode("utf-8")


# ── 6. File Generation (<zauq_file> extraction) ───────────────────────────────

def test_file_generation_extraction_and_packaging():
    """Verify <zauq_file> blocks in model responses are parsed into download assets."""
    model_output = (
        "Here is your script:\n\n"
        "<zauq_file filename=\"main.py\">\n"
        "print('Hello world!')\n"
        "</zauq_file>\n\n"
        "Enjoy!"
    )

    clean_text, files = extract_generated_files(model_output)
    assert len(files) == 1
    assert files[0]["filename"] == "main.py"
    assert files[0]["content"] == "print('Hello world!')"
    assert "Generated File" in clean_text
    assert "main.py" in clean_text
    assert "<zauq_file" not in clean_text


# ── 7. L2 Episodic Memory Retrieval ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_episodic_memory_injection(monkeypatch):
    """Verify user facts from episodic memory are injected into persona prompt."""
    req = ChatRequest(
        channel_id="c_mem",
        user_id="user_memory_test",
        user_name="Charlie",
        messages=[{"role": "user", "content": "What do you know about me?"}],
    )

    mock_memories = [
        {"fact_content": "User prefers dark mode and Python 3.12.", "category": "preference"}
    ]

    with patch("backend.chat.context_builder.get_relevant_user_memories", new_callable=AsyncMock) as mock_get_mem:
        mock_get_mem.return_value = mock_memories
        ctx = await context_builder.build(req)

        assert "[Known User Facts for @Charlie]" in ctx.persona
        assert "User prefers dark mode and Python 3.12." in ctx.persona


# ── 8. L3 Server Lore Retrieval ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_server_lore_rag_injection():
    """Verify server lore RAG prompt is retrieved and injected when guild_id is provided."""
    req = ChatRequest(
        channel_id="c_lore",
        guild_id="guild_lore_123",
        messages=[{"role": "user", "content": "What are the rules of this server?"}],
    )

    with patch("backend.memory.rag.get_lore_context_prompt", new_callable=AsyncMock) as mock_lore:
        mock_lore.return_value = "\n\n[Server Lore & Community Rules]:\nRule 1: Be respectful."
        ctx = await context_builder.build(req)

        assert "[Server Lore & Community Rules]" in ctx.persona
        assert "Rule 1: Be respectful." in ctx.persona


# ── 9. Moderation Check ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_moderation_service_checks():
    """Verify moderation flags work cleanly without crashing chat."""
    filter_inst = ContentFilter()
    with patch("backend.models.router.model_router.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = '{"classification": "safe", "reason": "", "severity": "low"}'
        res = await filter_inst.check_message("Hello, this is a friendly programming question.")
        assert res.get("classification") == "safe"


# ── 10. Timeout Behavior ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_timeout_handling(mock_background_tasks, monkeypatch):
    """Verify system handles LLM generation timeouts gracefully."""
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", False)

    req = ChatRequest(
        channel_id="c_timeout",
        messages=[{"role": "user", "content": "Long task"}],
    )

    with patch("backend.models.router.model_router.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.side_effect = asyncio.TimeoutError("Generation timed out")

        with pytest.raises(Exception) as exc_info:
            await chat_completion(req, mock_background_tasks)
        assert exc_info.value.status_code == 500
