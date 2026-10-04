from __future__ import annotations
import logging
import re
from typing import Any
from backend.search.models import (
    SearchResponse,
    SearchResult,
    FetchResult,
    EvidenceItem,
    ResearchResult,
)
from backend.search.cache import search_cache
from backend.search.fetcher import fetch_url, fetch_urls_parallel, is_safe_public_url
from backend.search.providers.serper import serper, SerperProvider
from backend.config import settings

logger = logging.getLogger("zauq.search.service")

# Query optimizer

_FILLER_PATTERNS = [
    re.compile(
        r'^(?:please\s+)?(?:can\s+you\s+)?'
        r'(?:search\s+(?:for|about|the\s+web\s+for)?|research\s+about|look\s+up'
        r'|find\s+information\s+on|tell\s+me\s+about|what\s+do\s+you\s+know\s+about|investigate|explore)\s+',
        re.IGNORECASE,
    ),
    re.compile(
        r'(?:,\s*)?(?:research\s+about\s+it\s+and\s+tell\s+me|tell\s+me\s+more'
        r'|give\s+me\s+details|explain\s+in\s+detail|and\s+give\s+citations)[.!?]*$',
        re.IGNORECASE,
    ),
]

_STOP_WORDS = frozenset({
    "a", "an", "the", "in", "on", "at", "of", "for", "to",
    "and", "or", "is", "are", "where", "it", "not", "allowed",
})


def optimize_queries(raw_query: str, max_queries: int = 3) -> list[str]:
    """
    Remove conversational filler and optionally generate a keyword variant.
    Returns 1-3 search queries, always starting with the cleaned version.
    """
    if not raw_query:
        return []
    cleaned = raw_query.strip()
    for pat in _FILLER_PATTERNS:
        cleaned = pat.sub("", cleaned).strip()
    if not cleaned:
        cleaned = raw_query.strip()

    queries = [cleaned]

    words = cleaned.split()
    if len(words) > 6:
        keywords = [w for w in words if w.lower() not in _STOP_WORDS and len(w) > 2]
        if len(keywords) >= 3:
            kw_query = " ".join(keywords[:7])
            if kw_query != cleaned:
                queries.append(kw_query)

    return queries[:max_queries]


# Search/should-search heuristic (preserved from v3)

_EXPLICIT_TRIGGERS = frozenset({
    "search", "look up", "find info", "find information", "find out",
    "browse the web", "check online", "google it", "google for",
    "search the web", "search online", "search for", "look on the web",
    "look online", "search up", "research about", "research on",
})
_TEMPORAL_KEYWORDS = frozenset({
    "latest", "news", "today", "yesterday", "tonight", "this week",
    "this month", "current", "release", "version", "price", "weather",
    "score", "match", "stock", "update", "released", "what happened",
    "recent", "who won", "upcoming", "schedule", "newest", "changelog",
})
_RESEARCH_KEYWORDS = frozenset({
    "research", "investigate", "compare", "benchmark", "analysis",
    "sources", "facts", "who created", "when did", "documentation",
    "github repo", "arxiv paper", "is it true that",
    "who is the current", "what is the current", "who is the new", "status of",
})


def should_search(query: str) -> bool:
    """
    Heuristic: does this query require a live web search?
    Preserved verbatim from v3 WebSearchEngine.should_search_web().
    """
    if not query or len(query.strip()) < 3:
        return False
    q = query.lower()
    if any(t in q for t in _EXPLICIT_TRIGGERS):
        return True
    if any(t in q for t in _TEMPORAL_KEYWORDS):
        return True
    if any(t in q for t in _RESEARCH_KEYWORDS):
        return True
    return False


def extract_urls(text: str) -> list[str]:
    """Extract all http/https URLs from free text."""
    if not text:
        return []
    return [u.rstrip('.,;:!?') for u in re.findall(r'https?://[^\s<>\[\]()"\x27`]+', text)]


# Evidence Extraction & Query Decomposition

_BOILERPLATE_PATTERNS = [
    re.compile(r'cookie|privacy policy|terms of (?:service|use)|all rights reserved|sign in|log in|subscribe', re.I),
    re.compile(r'javascript is disabled|enable javascript|browser not supported|accept all cookies', re.I),
]


def extract_evidence_excerpt(text: str, query: str, max_chars: int = 5000) -> str:
    """
    Distills high-value evidence excerpts from retrieved page text (Phase 10).
    Filters boilerplate, scores paragraphs by query keywords, and returns
    information-dense excerpts instead of raw webpage dumps.
    """
    if not text or len(text.strip()) < 20:
        return ""

    # Split into paragraphs / sections
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    # Filter out obvious boilerplate lines (cookies, sign in, terms of use)
    clean_paras = []
    for p in paragraphs:
        if len(p) < 300 and any(bp.search(p) for bp in _BOILERPLATE_PATTERNS):
            continue
        clean_paras.append(p)

    if not clean_paras:
        clean_paras = paragraphs

    # If filtered text is already concise and within budget, return directly
    joined_clean = "\n\n".join(clean_paras)
    if len(joined_clean) <= max_chars:
        return joined_clean

    # Extract keywords from query
    query_words = set(re.findall(r'\b[a-zA-Z0-9_-]{3,}\b', query.lower())) - _STOP_WORDS

    # Score paragraphs by query keyword density and heading indicators
    scored = []
    for idx, p in enumerate(clean_paras):
        p_lower = p.lower()
        score = sum(2 for w in query_words if w in p_lower)
        if p.startswith('#'):
            score += 3
        if idx < 3:
            score += 1
        scored.append((score, idx, p))

    # Sort by score descending to pick top sections
    top_picks = sorted(scored, key=lambda x: x[0], reverse=True)

    selected_indices = set()
    accumulated_len = 0

    for score, idx, p in top_picks:
        if score > 0 or len(selected_indices) < 2:
            if accumulated_len + len(p) <= max_chars:
                selected_indices.add(idx)
                accumulated_len += len(p)
            else:
                if accumulated_len < 1000:
                    selected_indices.add(idx)
                break

    if not selected_indices:
        selected_indices = set(range(min(3, len(clean_paras))))

    # Reconstruct text in natural reading order
    ordered_paras = [clean_paras[i] for i in sorted(selected_indices)]
    excerpt = "\n\n".join(ordered_paras)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars] + "\n...[Excerpt truncated]"
    return excerpt


def decompose_deep_research_queries(topic: str, max_queries: int = 3) -> list[str]:
    """
    Decomposes a broad research topic into up to 3 focused, complementary search queries.
    - Query 1: Clean core topic / overview
    - Query 2: Technical architecture / mechanics / specifications
    - Query 3: Recent updates / benchmarks / comparisons
    """
    cleaned = optimize_queries(topic, max_queries=1)
    base_q = cleaned[0] if cleaned else topic.strip()

    candidates = [
        base_q,
        f"{base_q} architecture details specifications",
        f"{base_q} overview benchmarks updates",
    ]
    return candidates[:max_queries]


# SearchService

class SearchService:
    """
    High-level search service consumed by:
    - backend/tools/native/web_tools.py (Phase 2)
    - backend/routers/chat.py (Phase 4 agent runtime integration)

    Routing: Serper only; missing credentials return an explicit unavailable error.

    All results go through the in-process TTL cache.
    """

    def __init__(self, provider: SerperProvider | None = None) -> None:
        self._serper = provider or serper

    # Core: search

    async def search(
        self,
        query: str,
        category: str = "all",
        max_results: int | None = None,
    ) -> SearchResponse:
        """
        Execute a web search, with caching.
        Returns an explicit error when Serper is unavailable.
        """
        n = max(1, min(max_results or settings.WEB_SEARCH_MAX_RESULTS, 10))
        provider_name = 'serper'
        if settings.WEB_SEARCH_PROVIDER != 'serper':
            return SearchResponse(query=query, category=category, error='Unsupported configured search provider; use serper', search_calls=0)

        cache_key = search_cache.make_key(provider_name, query, category, n)
        ttl = search_cache.ttl_for_category(category)
        cached = search_cache.get(cache_key, ttl=ttl)
        if cached is not None:
            logger.debug('Search cache hit category=%s', category)
            from dataclasses import replace
            return replace(cached, from_cache=True, search_calls=0)

        if self._serper.available:
            result = await self._serper.search(query, category=category, max_results=n)
        else:
            logger.warning('SERPER_API_KEY not configured. Web search unavailable.')
            result = SearchResponse(query=query, results=[], category=category, provider="serper", error='Search unavailable: SERPER_API_KEY is not configured', search_calls=0)

        if result.results and not result.error:
            search_cache.set(cache_key, result)
        return result

    # Core: fetch

    async def fetch(self, url: str, max_chars: int = 8000) -> FetchResult:
        """Fetch readable content from a single URL."""
        return await fetch_url(url, max_chars=max_chars)

    async def fetch_many(
        self,
        urls: list[str],
        max_chars_per_page: int = 4000,
        max_pages: int | None = None,
    ) -> list[FetchResult]:
        """Fetch multiple URLs concurrently."""
        safe_urls = [u for u in urls if is_safe_public_url(u)]
        return await fetch_urls_parallel(
            safe_urls,
            max_chars_per_page=max_chars_per_page,
            max_pages=max_pages,
        )

    # Research Mode v2 (Bounded Deep Research Engine)

    async def deep_research(
        self,
        topic: str,
        category: str = "all",
        max_queries: int = 3,
        max_pages: int = 5,
        total_char_limit: int = 40000,
    ) -> ResearchResult:
        """
        Phase 10: Bounded Deep Research Engine.
        1. Decomposes topic into max 3 focused queries.
        2. Executes Serper in parallel across queries.
        3. Deduplicates URLs across results (with 1 optional fallback query if 0 results).
        4. Fetches top max 5 pages concurrently (concurrency = 3).
        5. Extracts structured evidence excerpts, degrading to snippets on fetch failure.
        6. Enforces hard total character budget (35k-50k chars).
        7. Returns verified citations and structured ResearchResult.
        """
        import asyncio

        max_queries = max(1, min(int(max_queries), 3))
        max_pages = max(0, min(int(max_pages), 5))
        total_char_limit = max(0, min(int(total_char_limit), 50000))
        queries = decompose_deep_research_queries(topic, max_queries=max_queries)
        responses = await asyncio.gather(*[
            self.search(q, category=category, max_results=5) for q in queries
        ], return_exceptions=True)
        unique = {}
        search_calls = sum(1 if isinstance(r, Exception) else r.search_calls for r in responses)
        errors = [r.error for r in responses if isinstance(r, SearchResponse) and r.error]
        if any(isinstance(r, Exception) for r in responses):
            errors.append("A research search request failed.")
        for response in responses:
            if isinstance(response, SearchResponse):
                for result in response.results:
                    if result.url and is_safe_public_url(result.url):
                        unique.setdefault(result.url, result)
        # Retry an empty result set once; authentication/outage failures are not retried.
        if not unique and not errors:
            fallback_q = f"{topic.strip()} overview"
            if fallback_q in queries:
                fallback_q = f"{topic.strip()} info"
            response = await self.search(fallback_q, category=category, max_results=5)
            search_calls += response.search_calls
            queries.append(fallback_q)
            if response.error:
                errors.append(response.error)
            for result in response.results:
                if result.url and is_safe_public_url(result.url):
                    unique.setdefault(result.url, result)
        urls = list(unique)[:max_pages]
        fetched = await self.fetch_many(urls, max_chars_per_page=6000, max_pages=max_pages) if urls else []
        fetched_by_url = {r.url: r for r in fetched}
        evidence, citations, blocks = [], [], []
        accumulated = 0
        degraded = False
        for url in urls:
            result = unique[url]
            page = fetched_by_url.get(url)
            excerpt = extract_evidence_excerpt(page.content, topic, max_chars=5000) if page and page.success else ""
            verified = bool(excerpt)
            if not verified:
                degraded = True
                excerpt = result.snippet
            excerpt = excerpt[:max(0, total_char_limit - accumulated)]
            if not excerpt:
                continue
            title = result.title[:200]
            evidence.append(EvidenceItem(title, url, title, excerpt, fetched=verified))
            citations.append(f"• [{title[:60]}]({url})" + (" (search snippet only)" if not verified else ""))
            blocks.append(f"--- {'Fetched page' if verified else 'Search snippet only'}: {title} ({url}) ---\n{excerpt}")
            accumulated += len(excerpt)
        context = ("### 📑 Multi-Source Web Research Evidence:\n" + "\n".join(blocks))[:total_char_limit] if blocks else ""
        return ResearchResult(
            topic=topic, queries=queries, evidence=evidence, citations=citations,
            context_text=context, total_chars=accumulated, degraded=degraded,
            error="; ".join(dict.fromkeys(errors)) if errors and not evidence else None,
            search_calls=search_calls,
            pages_fetched=sum(bool(r.success and r.content.strip()) for r in fetched),
        )

    # Composite: search + fetch (Quick or Deep research)

    async def search_and_fetch(
        self,
        query: str,
        category: str = "all",
        max_results: int | None = None,
        fetch_top_n: int = 2,
        max_chars_per_page: int = 3500,
    ) -> dict[str, Any]:
        """
        Combined search + parallel page fetch.
        If fetch_top_n > 2, delegates to Phase 10 deep_research.
        If fetch_top_n <= 2, executes Quick Research (1 query, top 2 pages).
        """
        if fetch_top_n > 2:
            res = await self.deep_research(
                topic=query,
                category=category,
                max_pages=min(fetch_top_n, 5),
            )
            return {
                "query": query,
                "optimized_query": res.queries[0] if res.queries else query,
                "category": category,
                "results": [
                    {"title": ev.source_title, "url": ev.source_url, "snippet": ev.excerpt[:200]}
                    for ev in res.evidence
                ],
                "roamed_pages": [
                    {"title": ev.source_title, "url": ev.source_url, "content": ev.excerpt, "fetched": ev.fetched}
                    for ev in res.evidence
                ],
                "context_text": res.context_text,
                "citations": res.citations,
                "provider": "serper",
                "degraded": res.degraded,
                "error": res.error,
                "search_calls": res.search_calls,
                "pages_fetched": res.pages_fetched,
            }

        # Quick Research: 1 query, 5 results, top 2 pages with evidence excerpts
        n = max(1, min(max_results or settings.WEB_SEARCH_MAX_RESULTS, 10))
        cleaned_queries = optimize_queries(query, max_queries=1)
        primary_q = cleaned_queries[0] if cleaned_queries else query

        search_resp = await self.search(primary_q, category=category, max_results=n)

        citations = []
        for r in search_resp.results[:5]:
            label = (r.title[:60] + "...") if len(r.title) > 60 else r.title
            citations.append(f"• [{label}]({r.url})")

        fetched_pages = []
        fetch_top_n = max(0, min(fetch_top_n, 2))
        fetch_urls_list = [r.url for r in search_resp.results[:fetch_top_n] if r.url]
        if fetch_urls_list:
            fetch_results = await self.fetch_many(
                fetch_urls_list,
                max_chars_per_page=max_chars_per_page,
            )
            results_by_url = {r.url: r for r in search_resp.results}
            for fr in fetch_results:
                sr = results_by_url.get(fr.url)
                title = sr.title if sr else fr.url
                if fr.success and len(fr.content.strip()) >= 20:
                    excerpt = extract_evidence_excerpt(fr.content, query, max_chars=max_chars_per_page)
                    fetched_pages.append({
                        "title": title,
                        "url": fr.url,
                        "content": excerpt,
                        "fetched": True,
                    })
                elif sr and sr.snippet:
                    # Degradation to snippet on single-page fetch failure
                    fetched_pages.append({
                        "title": title,
                        "url": fr.url,
                        "content": sr.snippet,
                        "fetched": False,
                    })

        context_blocks = []
        if fetched_pages:
            context_blocks.append("### 📑 Full-Page Web Research Context:")
            for p in fetched_pages:
                context_blocks.append(f"--- {'Fetched page' if p['fetched'] else 'Search snippet only'}: {p['title']} ({p['url']}) ---\n{p['content']}\n")
        elif search_resp.results:
            context_blocks.append("### 🌐 Live Web Search Snippets:")
            for r in search_resp.results[:4]:
                context_blocks.append(f"• **{r.title}** ({r.url}):\n  {r.snippet}")

        return {
            "query": query,
            "optimized_query": primary_q,
            "category": category,
            "results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in search_resp.results
            ],
            "roamed_pages": fetched_pages,
            "context_text": "\n".join(context_blocks),
            "citations": citations,
            "provider": search_resp.provider,
            "from_cache": search_resp.from_cache,
            "search_calls": search_resp.search_calls,
            "pages_fetched": sum(p["fetched"] for p in fetched_pages),
            "error": search_resp.error,
        }


# Module-level singleton
search_service = SearchService()
