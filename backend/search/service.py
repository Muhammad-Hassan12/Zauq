from __future__ import annotations
import logging
import re
from typing import Any
from backend.search.models import SearchResponse, FetchResult
from backend.search.cache import search_cache
from backend.search.fetcher import fetch_url, fetch_urls_parallel, is_safe_public_url
from backend.search.providers.serper import serper, SerperProvider
from backend.config import settings

logger = logging.getLogger("zauq.search.service")

# ── Query optimizer ───────────────────────────────────────────────────────────

_FILLER_PATTERNS = [
    re.compile(
        r'^(?:please\s+)?(?:can\s+you\s+)?'
        r'(?:search\s+(?:for|about|the\s+web\s+for)?|research\s+about|look\s+up'
        r'|find\s+information\s+on|tell\s+me\s+about|what\s+do\s+you\s+know\s+about)\s+',
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


# ── Search/should-search heuristic (preserved from v3) ────────────────────────

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
    return re.findall(r'https?://(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?:/[^\s()<>]*)*', text)


# ── SearchService ─────────────────────────────────────────────────────────────

class SearchService:
    """
    High-level search service consumed by:
    - backend/tools/native/web_tools.py (Phase 2)
    - backend/routers/chat.py (Phase 4 agent runtime integration)

    Routing:
      SERPER_API_KEY set   -> Serper provider (primary)
      no key              -> DuckDuckGo legacy fallback (via web_search_engine)

    All results go through the in-process TTL cache.
    """

    def __init__(self, provider: SerperProvider | None = None) -> None:
        self._serper = provider or serper

    # ── Core: search ─────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        category: str = "all",
        max_results: int | None = None,
    ) -> SearchResponse:
        """
        Execute a web search, with caching.
        Routes to Serper when key is available, DuckDuckGo otherwise.
        """
        n = max_results or settings.WEB_SEARCH_MAX_RESULTS
        provider_name = "serper" if self._serper.available else "duckduckgo"

        cache_key = search_cache.make_key(provider_name, query, category, n)
        ttl = search_cache.ttl_for_category(category)
        cached = search_cache.get(cache_key, ttl=ttl)
        if cached is not None:
            logger.debug(f"Cache hit for query='{query}' category={category}")
            cached.from_cache = True
            return cached

        if self._serper.available:
            result = await self._serper.search(query, category=category, max_results=n)
        else:
            result = await self._duckduckgo_fallback(query, category, n)

        if result.results:
            search_cache.set(cache_key, result)
        return result

    async def _duckduckgo_fallback(
        self,
        query: str,
        category: str,
        max_results: int,
    ) -> SearchResponse:
        """
        Delegate to the legacy WebSearchEngine (DuckDuckGo HTML scraper).
        Translates its output into a normalized SearchResponse.
        """
        try:
            from backend.integrations.web_search import web_search_engine
            filtered_q = web_search_engine.apply_category_filter(query, category)
            raw = await web_search_engine.search_duckduckgo(filtered_q, max_results=max_results)
            results = [
                SearchResult(
                    title=r.get("title", "Untitled"),
                    url=r.get("url", ""),
                    snippet=r.get("snippet", ""),
                    position=idx + 1,
                    source="duckduckgo",
                )
                for idx, r in enumerate(raw)
                if r.get("url")
            ]
            return SearchResponse(
                query=query,
                results=results,
                category=category,
                provider="duckduckgo",
            )
        except Exception as exc:
            logger.exception(f"DuckDuckGo fallback failed for query='{query}': {exc}")
            return SearchResponse(query=query, results=[], category=category, provider="duckduckgo")

    # ── Core: fetch ───────────────────────────────────────────────────────────

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

    # ── Composite: search + fetch (for chat context enrichment) ───────────────

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
        Returns a context dict ready for LLM prompt injection.

        Identical semantic contract to the v3 deep_search_and_roam() output
        so chat.py's injection block needs no change.
        """
        n = max_results or settings.WEB_SEARCH_MAX_RESULTS
        cleaned_queries = optimize_queries(query)
        primary_q = cleaned_queries[0]

        search_resp = await self.search(primary_q, category=category, max_results=n)

        # Category fallback if no results
        if not search_resp.results and category != "all":
            search_resp = await self.search(primary_q, category="all", max_results=n)

        # Build citation list
        citations = []
        for r in search_resp.results[:5]:
            label = (r.title[:60] + "...") if len(r.title) > 60 else r.title
            citations.append(f"• [{label}]({r.url})")

        # Fetch top N pages in parallel (SSRF-filtered inside fetch_many)
        fetched_pages = []
        fetch_urls_list = [r.url for r in search_resp.results[:fetch_top_n] if r.url]
        if fetch_urls_list:
            fetch_results = await self.fetch_many(
                fetch_urls_list,
                max_chars_per_page=max_chars_per_page,
            )
            for idx, fr in enumerate(fetch_results):
                if fr.success and len(fr.content.strip()) > 100:
                    fetched_pages.append({
                        "title": search_resp.results[idx].title if idx < len(search_resp.results) else fr.url,
                        "url": fr.url,
                        "content": fr.content.strip(),
                    })

        # Build context block (same format as v3 for chat.py compatibility)
        context_blocks: list[str] = []
        if fetched_pages:
            context_blocks.append("### 📑 Full-Page Web Research Context:")
            for p in fetched_pages:
                context_blocks.append(f"--- Source: {p['title']} ({p['url']}) ---\n{p['content']}\n")
        elif search_resp.results:
            context_blocks.append("### 🌐 Live Web Search Snippets:")
            for r in search_resp.results[:4]:
                context_blocks.append(f"• **{r.title}** ({r.url}):\n  {r.snippet}")

        context_text = "\n".join(context_blocks)

        return {
            "query": query,
            "optimized_query": primary_q,
            "category": category,
            "results": [
                {"title": r.title, "url": r.url, "snippet": r.snippet}
                for r in search_resp.results
            ],
            "roamed_pages": fetched_pages,
            "context_text": context_text,
            "citations": citations,
            "provider": search_resp.provider,
            "from_cache": search_resp.from_cache,
        }


# Module-level singleton
search_service = SearchService()
