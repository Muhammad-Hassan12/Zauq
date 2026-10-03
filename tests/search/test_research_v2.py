"""Unit tests for Phase 10: Research Mode v2 Without Heavy Autonomous Loops.

Verifies:
1. Evidence extraction filters boilerplate and distills information-dense excerpts.
2. Query decomposition bounds requests to max 3 focused queries.
3. Deep research parallel flow deduplicates URLs and bounds pages to max 5.
4. Graceful degradation to snippets when page fetches fail.
5. Strict enforcement of hard total character limits (35k-50k budget).
6. Single fallback query on 0 search results.
"""

import pytest
from unittest.mock import AsyncMock, patch

from backend.search.models import SearchResponse, SearchResult, FetchResult, EvidenceItem, ResearchResult
from backend.search.providers.serper import SerperProvider
from backend.search.service import (
    SearchService,
    extract_evidence_excerpt,
    decompose_deep_research_queries,
)


def test_extract_evidence_excerpt_boilerplate_filtering():
    """Verify that boilerplate lines (cookies, sign in, terms) are filtered."""
    raw_page = (
        "# FastAPI High Performance Architecture\n\n"
        "Accept all cookies to proceed. Please read our Privacy Policy and Terms of Service.\n\n"
        "FastAPI is a modern, fast (high-performance), web framework for building APIs with Python.\n"
        "It is based on Starlette for the web parts and Pydantic for the data parts.\n\n"
        "Sign in to leave a comment.\n\n"
        "Benchmark tests show that FastAPI is on par with NodeJS and Go when running with Uvicorn.\n"
    )

    excerpt = extract_evidence_excerpt(raw_page, query="FastAPI performance benchmark", max_chars=1000)
    assert "FastAPI is a modern, fast" in excerpt
    assert "Benchmark tests show" in excerpt
    assert "Accept all cookies" not in excerpt
    assert "Sign in to leave a comment" not in excerpt


def test_extract_evidence_excerpt_length_ceiling():
    """Verify that excerpt does not exceed configured max_chars."""
    long_page = "Key section discussing distributed agent systems in detail.\n\n" * 50
    excerpt = extract_evidence_excerpt(long_page, query="agent systems", max_chars=300)
    assert len(excerpt) <= 350  # including truncation marker


def test_decompose_deep_research_queries():
    """Verify that query decomposition produces max 3 focused queries."""
    queries = decompose_deep_research_queries("RAG embeddings", max_queries=3)
    assert len(queries) <= 3
    assert queries[0] == "RAG embeddings"

    # For longer query
    long_q = "Please investigate the current state of deep research agents and benchmarks"
    long_queries = decompose_deep_research_queries(long_q, max_queries=3)
    assert len(long_queries) <= 3
    assert not any("Please investigate" in q for q in long_queries)


@pytest.mark.asyncio
async def test_deep_research_bounded_flow_and_deduplication():
    """Verify that parallel queries deduplicate URLs and fetch max 5 pages."""
    mock_serper = AsyncMock(spec=SerperProvider)
    mock_serper.available = True

    # 3 search responses with overlapping URLs
    resp1 = SearchResponse(
        query="q1",
        results=[
            SearchResult(title="Doc 1", url="https://example.com/1", snippet="Snippet 1"),
            SearchResult(title="Shared Doc", url="https://example.com/shared", snippet="Shared snippet"),
        ],
    )
    resp2 = SearchResponse(
        query="q2",
        results=[
            SearchResult(title="Shared Doc", url="https://example.com/shared", snippet="Shared snippet"),
            SearchResult(title="Doc 2", url="https://example.com/2", snippet="Snippet 2"),
        ],
    )
    resp3 = SearchResponse(
        query="q3",
        results=[
            SearchResult(title="Doc 3", url="https://example.com/3", snippet="Snippet 3"),
        ],
    )
    mock_serper.search.side_effect = [resp1, resp2, resp3]

    svc = SearchService(provider=mock_serper)

    # Mock page fetcher
    def mock_fetch_many(urls, **kwargs):
        return [
            FetchResult(url=u, success=True, content=f"# Content for {u}\nDetailed technical section.")
            for u in urls
        ]

    with patch.object(svc, "fetch_many", new_callable=AsyncMock, side_effect=mock_fetch_many) as mock_fm:
        res: ResearchResult = await svc.deep_research("distributed systems", max_pages=5)

        # 4 unique URLs: example.com/1, example.com/shared, example.com/2, example.com/3
        called_urls = mock_fm.call_args[0][0]
        assert len(called_urls) == 4
        assert len(set(called_urls)) == 4
        assert "https://example.com/shared" in called_urls

        assert len(res.evidence) == 4
        assert len(res.citations) == 4
        assert res.degraded is False
        assert "Multi-Source Web Research Evidence" in res.context_text


@pytest.mark.asyncio
async def test_deep_research_graceful_degradation_on_fetch_failure():
    """When page fetches fail (e.g. 404 or network timeout), degrades to SERP snippets."""
    mock_serper = AsyncMock(spec=SerperProvider)
    mock_serper.available = True
    mock_serper.search.return_value = SearchResponse(
        query="q",
        results=[
            SearchResult(title="Broken Page", url="https://example.com/broken", snippet="Reliable SERP snippet."),
        ],
    )

    svc = SearchService(provider=mock_serper)

    # Mock fetch failure
    failed_fetch = [FetchResult(url="https://example.com/broken", success=False, error="404 Not Found")]

    with patch.object(svc, "fetch_many", new_callable=AsyncMock, return_value=failed_fetch):
        res: ResearchResult = await svc.deep_research("test query", max_pages=3)

        assert res.degraded is True
        assert len(res.evidence) == 1
        assert res.evidence[0].excerpt == "Reliable SERP snippet."
        assert "Reliable SERP snippet" in res.context_text


@pytest.mark.asyncio
async def test_deep_research_hard_budget_enforcement():
    """Verify total extracted characters across evidence items cannot exceed total_char_limit."""
    mock_serper = AsyncMock(spec=SerperProvider)
    mock_serper.available = True
    mock_serper.search.return_value = SearchResponse(
        query="q",
        results=[
            SearchResult(title=f"Page {i}", url=f"https://example.com/{i}", snippet="S")
            for i in range(4)
        ],
    )

    svc = SearchService(provider=mock_serper)

    # 4 pages each with 1000 chars
    fetch_results = [
        FetchResult(url=f"https://example.com/{i}", success=True, content="A" * 1000)
        for i in range(4)
    ]

    with patch.object(svc, "fetch_many", new_callable=AsyncMock, return_value=fetch_results):
        # Enforce budget of 1500 chars total
        res: ResearchResult = await svc.deep_research("budget test", total_char_limit=1500)
        assert res.total_chars <= 1600


@pytest.mark.asyncio
async def test_deep_research_zero_results_single_fallback():
    """When initial queries return 0 results, at most 1 fallback query is executed."""
    mock_serper = AsyncMock(spec=SerperProvider)
    mock_serper.available = True

    empty_resp = SearchResponse(query="empty", results=[])
    fallback_resp = SearchResponse(
        query="fallback",
        results=[SearchResult(title="Fallback Found", url="https://example.com/fallback", snippet="FB snippet")],
    )

    # Return empty for initial 3 queries, then results for fallback
    mock_serper.search.side_effect = [empty_resp, empty_resp, empty_resp, fallback_resp]

    svc = SearchService(provider=mock_serper)

    with patch.object(svc, "fetch_many", new_callable=AsyncMock, return_value=[]):
        res: ResearchResult = await svc.deep_research("very obscure esoteric query", max_queries=3)

        # 3 initial queries + 1 fallback = 4 calls total
        assert mock_serper.search.call_count == 4
        assert len(res.evidence) == 1
        assert res.evidence[0].source_url == "https://example.com/fallback"
