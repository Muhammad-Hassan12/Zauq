from unittest.mock import AsyncMock

import pytest

from backend.search.models import SearchResponse, SearchResult, FetchResult
from backend.search.service import SearchService


@pytest.mark.asyncio
async def test_outage_has_no_fake_evidence_or_retry():
    service = SearchService()
    service.search = AsyncMock(return_value=SearchResponse('query',error='Search unavailable'))
    result = await service.deep_research('topic')
    assert result.context_text == ''
    assert result.error == 'Search unavailable'
    assert service.search.await_count == 3


@pytest.mark.asyncio
async def test_missing_key_makes_zero_provider_calls(monkeypatch):
    from backend.search.providers.serper import SerperProvider
    service = SearchService(provider=SerperProvider(api_key=''))
    result = await service.search_and_fetch('query')
    assert result['search_calls'] == 0
    assert result['error']


@pytest.mark.asyncio
async def test_hard_bounds_and_snippet_attribution():
    service = SearchService()
    service.search = AsyncMock(return_value=SearchResponse('q', results=[SearchResult(str(i),f'https://example.com/{i}','snippet '*10000) for i in range(20)]))
    service.fetch_many = AsyncMock(return_value=[FetchResult(f'https://example.com/{i}',False) for i in range(5)])
    result = await service.deep_research('topic',max_queries=999,max_pages=999,total_char_limit=999999)
    assert service.search.await_count == 3
    assert len(service.fetch_many.call_args.args[0]) == 5
    assert len(result.context_text) <= 50000
    assert sum(len(e.excerpt) for e in result.evidence) <= 50000
    assert all(not e.fetched for e in result.evidence)
    assert all('search snippet only' in c for c in result.citations)


@pytest.mark.asyncio
async def test_category_is_never_silently_widened():
    service = SearchService()
    service.search = AsyncMock(return_value=SearchResponse('q'))
    await service.search_and_fetch('query',category='arxiv')
    assert service.search.await_count == 1
    assert service.search.call_args.kwargs['category'] == 'arxiv'


def test_unknown_citations_are_removed_without_changing_code_examples():
    from backend.search.citations import validate_citations
    answer = '[Known](https://example.com/a) [Invented](https://unknown.example/a)\n```md\n[Example](https://unknown.example/a)\n```'
    result = validate_citations(answer,{'https://example.com/a'})
    assert '[Known](https://example.com/a)' in result
    assert 'Invented (unverified source omitted)' in result
    assert '[Example](https://unknown.example/a)' in result
