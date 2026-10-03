"""
Phase 2 tests for the search package.

All tests are fully offline — no real network calls.
Serper/httpx is mocked via unittest.mock.
"""
from __future__ import annotations
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.search.models import SearchResult, SearchResponse, FetchResult
from backend.search.cache import SearchCache, _make_cache_key
from backend.search.fetcher import is_safe_public_url
from backend.search.providers.serper import SerperProvider
from backend.search.service import SearchService, optimize_queries, should_search, extract_urls


# ── SearchResult / SearchResponse ─────────────────────────────────────────────

class TestSearchModels:
    def test_search_result_to_text(self):
        r = SearchResult(title="Python Docs", url="https://docs.python.org", snippet="The official Python docs.")
        text = r.to_text()
        assert "Python Docs" in text
        assert "docs.python.org" in text

    def test_search_result_to_text_no_url(self):
        r = SearchResult(title="Test", url="https://example.com", snippet="A snippet.")
        assert "example.com" not in r.to_text(include_url=False)

    def test_search_response_urls(self):
        resp = SearchResponse(
            query="test",
            results=[
                SearchResult(title="A", url="https://a.com", snippet=""),
                SearchResult(title="B", url="https://b.com", snippet=""),
            ],
        )
        assert resp.urls == ["https://a.com", "https://b.com"]

    def test_search_response_context_block_empty(self):
        resp = SearchResponse(query="test", results=[])
        assert resp.to_context_block() == ""

    def test_search_response_context_block(self):
        resp = SearchResponse(
            query="python asyncio",
            results=[SearchResult(title="A", url="https://a.com", snippet="Async stuff.")],
        )
        block = resp.to_context_block()
        assert "python asyncio" in block
        assert "https://a.com" in block

    def test_fetch_result_char_count(self):
        fr = FetchResult(url="https://x.com", success=True, content="hello world")
        assert fr.char_count == 11


# ── SearchCache ───────────────────────────────────────────────────────────────

class TestSearchCache:
    def test_cache_miss_on_empty(self):
        cache = SearchCache(max_entries=10)
        assert cache.get("missing_key", ttl=300) is None

    def test_cache_set_and_get(self):
        cache = SearchCache(max_entries=10)
        cache.set("k1", {"data": 42})
        assert cache.get("k1", ttl=300) == {"data": 42}

    def test_cache_eviction_at_capacity(self):
        cache = SearchCache(max_entries=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)   # triggers eviction of "a"
        assert cache.get("a", ttl=300) is None
        assert cache.get("d", ttl=300) == 4

    def test_cache_stats(self):
        cache = SearchCache()
        cache.set("x", "val")
        cache.get("x", ttl=300)   # hit
        cache.get("y", ttl=300)   # miss
        assert cache.stats["hits"] == 1
        assert cache.stats["misses"] == 1

    def test_cache_ttl_for_category(self):
        cache = SearchCache()
        assert cache.ttl_for_category("news") == 90
        assert cache.ttl_for_category("arxiv") == 1800
        assert cache.ttl_for_category("all") == 300

    def test_make_key_deterministic(self):
        k1 = _make_cache_key("serper", "python", "all", 5)
        k2 = _make_cache_key("serper", "python", "all", 5)
        assert k1 == k2

    def test_make_key_differs_on_query(self):
        k1 = _make_cache_key("serper", "python", "all", 5)
        k2 = _make_cache_key("serper", "javascript", "all", 5)
        assert k1 != k2

    def test_cache_clear(self):
        cache = SearchCache()
        cache.set("a", 1)
        cache.clear()
        assert cache.stats["entries"] == 0


# ── SSRF guard ────────────────────────────────────────────────────────────────

class TestSSRFGuard:
    def test_empty_url_blocked(self):
        assert is_safe_public_url("") is False

    def test_non_http_scheme_blocked(self):
        assert is_safe_public_url("ftp://example.com") is False
        assert is_safe_public_url("file:///etc/passwd") is False

    def test_localhost_blocked(self):
        assert is_safe_public_url("http://localhost/admin") is False
        assert is_safe_public_url("http://127.0.0.1/") is False

    def test_metadata_endpoint_blocked(self):
        assert is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False
        assert is_safe_public_url("http://metadata.google.internal/") is False

    def test_valid_public_url(self):
        # This makes a real DNS resolution — mock it for CI
        import socket
        with patch("socket.getaddrinfo", return_value=[
            (2, 1, 6, "", ("93.184.216.34", 80))  # example.com public IP
        ]):
            assert is_safe_public_url("https://example.com/page") is True


# ── optimize_queries ─────────────────────────────────────────────────────────

class TestOptimizeQueries:
    def test_strips_filler(self):
        queries = optimize_queries("search for the latest Python news")
        assert queries[0] == "the latest Python news"

    def test_short_query_no_keyword_variant(self):
        queries = optimize_queries("Python asyncio")
        assert len(queries) == 1
        assert queries[0] == "Python asyncio"

    def test_long_query_generates_keyword_variant(self):
        long_q = "what is the latest stable release of the Django web framework"
        queries = optimize_queries(long_q)
        assert len(queries) >= 2

    def test_empty_returns_empty(self):
        assert optimize_queries("") == []

    def test_max_queries_cap(self):
        queries = optimize_queries("very long very detailed query about python async stuff", max_queries=1)
        assert len(queries) == 1


# ── should_search ─────────────────────────────────────────────────────────────

class TestShouldSearch:
    def test_explicit_trigger(self):
        assert should_search("search for python tutorials") is True

    def test_temporal_keyword(self):
        assert should_search("what is the latest version of FastAPI?") is True

    def test_research_keyword(self):
        assert should_search("who created FastAPI?") is True

    def test_casual_chat_no_search(self):
        assert should_search("hello how are you") is False

    def test_empty_no_search(self):
        assert should_search("") is False


# ── extract_urls ──────────────────────────────────────────────────────────────

class TestExtractUrls:
    def test_extracts_single_url(self):
        urls = extract_urls("Check out https://example.com for info")
        assert "https://example.com" in urls

    def test_extracts_multiple_urls(self):
        text = "Visit https://a.com and https://b.org/page"
        urls = extract_urls(text)
        assert len(urls) == 2

    def test_empty_text_returns_empty(self):
        assert extract_urls("") == []

    def test_no_urls_returns_empty(self):
        assert extract_urls("no links here") == []


# ── SerperProvider ────────────────────────────────────────────────────────────

class TestSerperProvider:
    def test_available_false_without_key(self):
        p = SerperProvider(api_key="")
        assert p.available is False

    def test_available_true_with_key(self):
        p = SerperProvider(api_key="test_key_abc")
        assert p.available is True

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_key(self):
        p = SerperProvider(api_key="")
        resp = await p.search("python asyncio")
        assert isinstance(resp, SearchResponse)
        assert resp.results == []

    @pytest.mark.asyncio
    async def test_search_parses_organic_results(self):
        p = SerperProvider(api_key="fake_key_xyz")
        mock_data = {
            "organic": [
                {"title": "Python Docs", "link": "https://docs.python.org", "snippet": "Official Python docs."},
                {"title": "RealPython", "link": "https://realpython.com", "snippet": "Python tutorials."},
            ]
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_data

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            resp = await p.search("python docs", category="all", max_results=5)

        assert len(resp.results) == 2
        assert resp.results[0].title == "Python Docs"
        assert resp.results[0].url == "https://docs.python.org"
        assert resp.provider == "serper"

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_http_error(self):
        p = SerperProvider(api_key="fake_key_xyz")
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            resp = await p.search("test query")

        assert resp.results == []


# ── SearchService ─────────────────────────────────────────────────────────────

class TestSearchService:
    @pytest.mark.asyncio
    async def test_returns_cached_result(self):
        """Second call with same params must return from cache."""
        mock_serper = AsyncMock(spec=SerperProvider)
        mock_serper.available = True
        fake_resp = SearchResponse(
            query="cached query",
            results=[SearchResult(title="T", url="https://t.com", snippet="S")],
        )
        mock_serper.search = AsyncMock(return_value=fake_resp)

        svc = SearchService(provider=mock_serper)
        resp1 = await svc.search("cached query")
        resp2 = await svc.search("cached query")

        # Second call reads from cache — Serper is called only once
        assert mock_serper.search.call_count == 1
        assert resp2.from_cache is True

    @pytest.mark.asyncio
    async def test_fetch_returns_fetch_result(self):
        svc = SearchService()
        with patch("backend.search.service.fetch_url", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = FetchResult(url="https://x.com", success=True, content="page text")
            result = await svc.fetch("https://x.com")
        assert result.success is True
        assert result.content == "page text"
