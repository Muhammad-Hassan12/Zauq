"""Tests for Phase 9: Refactor Chat/Search Into a Single Orchestration Path.

Verifies:
1. web_search_engine compatibility facade delegates to backend.search.service without DuckDuckGo HTML scraping.
2. Search deduplication guard in model_router prevents redundant search calls when context is already enriched.
3. Gemini native grounding is disabled for standard research (Option A) and active only when GEMINI_NATIVE_GROUNDING_ENABLED is set (Option B).
4. Orchestrator records search in tool_trace for user-visible response transparency.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import BackgroundTasks

from backend.integrations.web_search import web_search_engine
from backend.search.service import search_service
from backend.search.models import SearchResponse, SearchResult, FetchResult
from backend.models.router import model_router
from backend.models.gemini_client import gemini_client
from backend.chat.orchestrator import ChatOrchestrator
from backend.chat.context_builder import ChatContext
from backend.config import settings


@pytest.mark.asyncio
async def test_web_search_engine_facade_delegation():
    """Verify that legacy WebSearchEngine methods delegate directly to SearchService."""
    mock_search_resp = SearchResponse(
        query="test query",
        results=[
            SearchResult(title="Result 1", url="https://example.com/1", snippet="Snippet 1", position=1, source="serper")
        ],
        category="all",
        provider="serper",
    )
    mock_fetch_res = FetchResult(
        url="https://example.com/page",
        success=True,
        content="# Page Title\nSample page content.",
    )
    mock_composite = {
        "query": "test query",
        "optimized_query": "test query",
        "category": "all",
        "results": [{"title": "Result 1", "url": "https://example.com/1", "snippet": "Snippet 1"}],
        "roamed_pages": [{"title": "Result 1", "url": "https://example.com/1", "content": "Sample content"}],
        "context_text": "### 📑 Full-Page Web Research Context:\nSample content",
        "citations": ["• [Result 1](https://example.com/1)"],
    }

    with patch.object(search_service, "search", new_callable=AsyncMock, return_value=mock_search_resp) as mock_search:
        results = await web_search_engine.search_duckduckgo("test query", max_results=3)
        assert len(results) == 1
        assert results[0]["title"] == "Result 1"
        assert results[0]["url"] == "https://example.com/1"
        mock_search.assert_awaited_once_with(query="test query", max_results=3)

    with patch.object(search_service, "fetch", new_callable=AsyncMock, return_value=mock_fetch_res) as mock_fetch:
        text = await web_search_engine.fetch_url_content("https://example.com/page")
        assert "Sample page content" in text
        mock_fetch.assert_awaited_once_with("https://example.com/page", max_chars=8000)

    with patch.object(search_service, "search_and_fetch", new_callable=AsyncMock, return_value=mock_composite) as mock_saf:
        data = await web_search_engine.deep_search_and_roam("test query", max_results=5, roam_top_n=2, category="github")
        assert "context_text" in data
        assert len(data["roamed_pages"]) == 1
        mock_saf.assert_awaited_once_with(query="test query", max_results=5, fetch_top_n=2, category="github")


@pytest.mark.asyncio
async def test_search_deduplication_guard_in_model_router():
    """Verify that model_router._handle_search_context does not execute when web evidence is already present."""
    messages_with_evidence = [
        {
            "role": "user",
            "content": "What is Python 3.12?\n\n[Live Deep Web Research Context for 'Python 3.12']:\nSome context",
        }
    ]

    with patch.object(search_service, "search_and_fetch", new_callable=AsyncMock) as mock_search:
        await model_router._handle_search_context(messages_with_evidence, enable_search=True)
        # Should NOT have called search_and_fetch because marker is present
        mock_search.assert_not_awaited()

    # Clean message without evidence should trigger search
    clean_messages = [{"role": "user", "content": "What is Python 3.12?"}]
    mock_data = {"context_text": "Python 3.12 was released recently."}
    with patch.object(search_service, "search_and_fetch", new_callable=AsyncMock, return_value=mock_data) as mock_search:
        await model_router._handle_search_context(clean_messages, enable_search=True)
        mock_search.assert_awaited_once()
        assert "[Live Deep Web Research Context" in clean_messages[0]["content"]


def test_gemini_grounding_option_a_and_b(monkeypatch):
    """Option A: Google grounding disabled for standard unified search.
    Option B: Google grounding enabled only when GEMINI_NATIVE_GROUNDING_ENABLED is true.
    """
    messages = [{"role": "user", "content": "Hello"}]

    # Option A (default: unified search, native grounding off)
    monkeypatch.setattr(settings, "GEMINI_NATIVE_GROUNDING_ENABLED", False)
    payload_a = gemini_client._prepare_payload(messages=messages, enable_search=True)
    assert "tools" not in payload_a

    # Option B (explicitly opted in to native Gemini grounding)
    monkeypatch.setattr(settings, "GEMINI_NATIVE_GROUNDING_ENABLED", True)
    payload_b = gemini_client._prepare_payload(messages=messages, enable_search=True)
    assert "tools" in payload_b
    assert payload_b["tools"] == [{"googleSearch": {}}]


@pytest.mark.asyncio
async def test_orchestrator_search_enrichment_and_transparency(monkeypatch):
    """Verify that orchestrator search sets tool_trace and disables secondary search."""
    monkeypatch.setattr(settings, "AGENT_RUNTIME_ENABLED", False)

    mock_req = MagicMock()
    mock_req.channel_id = "ch-1"
    mock_req.guild_id = "g-1"
    mock_req.user_id = "u-1"
    mock_req.user_name = "User"
    mock_req.mode_override = None
    mock_req.attachments = None
    mock_req.enable_web_search = True
    mock_req.deep_search = False
    mock_req.search_category = "all"
    mock_req.search_query = "latest AI news"
    mock_req.messages = [{"role": "user", "content": "latest AI news"}]

    ctx = ChatContext(
        persona="You are Zauq",
        mode="dev",
        temperature=0.2,
        provider="gemini",
        model_name="gemini-2.5-flash",
        enable_search=True,
        thinking_enabled=False,
        allow_code_exec=True,
        media_parts=[],
        working_messages=[{"role": "user", "content": "latest AI news"}],
    )

    mock_cb = MagicMock()
    mock_cb.build = AsyncMock(return_value=ctx)

    mock_router = MagicMock()
    mock_router.generate = AsyncMock(return_value="Here is the latest AI news.")

    mock_search_data = {
        "context_text": "AI model release details here.",
        "results": [{"title": "AI News", "url": "https://ai.example.com", "snippet": "New release"}],
    }

    orchestrator = ChatOrchestrator(context_builder_inst=mock_cb, router=mock_router)

    with patch.object(search_service, "search_and_fetch", new_callable=AsyncMock, return_value=mock_search_data):
        bg = BackgroundTasks()
        res = await orchestrator.run(mock_req, bg)

        assert res["response"] == "Here is the latest AI news."
        assert "tool_trace" in res
        assert len(res["tool_trace"]) == 1
        assert res["tool_trace"][0]["tool"] == "web.search"
        assert res["tool_trace"][0]["success"] is True

        # Verify that secondary search flag passed to model_router was False (prevent duplicate search)
        call_kwargs = mock_router.generate.call_args[1]
        assert call_kwargs["enable_search"] is False
