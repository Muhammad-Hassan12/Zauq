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

# ── Query optimizer ───────────────────────────────────────────────────────────

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


# ── Evidence Extraction & Query Decomposition (Phase 10) ──────────────────────

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
            logger.warning(f"SERPER_API_KEY not configured. Web search unavailable for '{query}'.")
            result = SearchResponse(query=query, results=[], category=category, provider="serper")

        if result.results:
            search_cache.set(cache_key, result)
        return result

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

    # ── Phase 10: Research Mode v2 (Bounded Deep Research Engine) ───────────

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

        # 1. Generate max 3 focused queries
        queries = decompose_deep_research_queries(topic, max_queries=min(max_queries, 3))

        # 2. Parallel Serper search
        search_tasks = [
            self.search(q, category=category, max_results=5)
            for q in queries
        ]
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        # 3. Deduplicate URLs across all queries
        unique_results_map: dict[str, SearchResult] = {}
        for res in search_results:
            if isinstance(res, SearchResponse):
                for r in res.results:
                    if r.url and is_safe_public_url(r.url) and r.url not in unique_results_map:
                        unique_results_map[r.url] = r

        # Fallback query if 0 results found (max 1 fallback attempt per Phase 10 budget)
        if not unique_results_map:
            logger.info(f"0 results from initial {len(queries)} queries. Trying 1 fallback query.")
            keywords = [w for w in topic.split() if w.lower() not in _STOP_WORDS and len(w) > 2]
            fallback_candidates = []
            if len(keywords) > 2:
                fallback_candidates.append(" ".join(keywords[:3]))
                fallback_candidates.append(" ".join(keywords[-3:]))
            if len(keywords) >= 2:
                fallback_candidates.append(f"{keywords[0]} {keywords[1]}")
            elif keywords:
                fallback_candidates.append(keywords[0])
            fallback_candidates.append(f"{topic} overview")

            fallback_q = None
            for cand in fallback_candidates:
                if cand and cand not in queries:
                    fallback_q = cand
                    break

            if not fallback_q:
                fallback_q = f"{topic} info"

            fb_res = await self.search(fallback_q, category=category, max_results=5)
            for r in fb_res.results:
                if r.url and is_safe_public_url(r.url) and r.url not in unique_results_map:
                    unique_results_map[r.url] = r
            queries.append(fallback_q)

        candidate_urls = list(unique_results_map.keys())[:max_pages]

        # 4. Fetch max 5 pages concurrently
        fetched_map: dict[str, FetchResult] = {}
        if candidate_urls:
            fetch_results = await self.fetch_many(
                candidate_urls,
                max_chars_per_page=6000,
                max_pages=max_pages,
            )
            for fr in fetch_results:
                fetched_map[fr.url] = fr

        # 5. Source / Evidence Extraction with graceful degradation
        evidence_items: list[EvidenceItem] = []
        citations: list[str] = []
        degraded = False
        accumulated_chars = 0

        for url in candidate_urls:
            sr = unique_results_map[url]
            fr = fetched_map.get(url)

            # Build verified citation
            clean_title = (sr.title[:60] + "...") if len(sr.title) > 60 else sr.title
            citations.append(f"• [{clean_title}]({url})")

            # Check if fetch was successful and substantive
            excerpt = ""
            if fr and fr.success and fr.content and len(fr.content.strip()) >= 20:
                excerpt = extract_evidence_excerpt(fr.content, topic, max_chars=5000)

            if excerpt:
                # Substantive page content retrieved
                pass
            else:
                # Graceful degradation to snippet
                degraded = True
                excerpt = sr.snippet or f"Summary for {sr.title}"

            # Check total character ceiling (35k - 50k chars)
            if accumulated_chars + len(excerpt) > total_char_limit:
                allowed_chars = max(0, total_char_limit - accumulated_chars)
                if allowed_chars > 200:
                    excerpt = excerpt[:allowed_chars] + "\n...[Evidence budget cap reached]"
                    evidence_items.append(
                        EvidenceItem(
                            claim=sr.title,
                            source_url=url,
                            source_title=sr.title,
                            excerpt=excerpt,
                        )
                    )
                break

            evidence_items.append(
                EvidenceItem(
                    claim=sr.title,
                    source_url=url,
                    source_title=sr.title,
                    excerpt=excerpt,
                )
            )
            accumulated_chars += len(excerpt)

        # 6. Assemble rich context text
        context_blocks = ["### 📑 Multi-Source Web Research Evidence:"]
        for ev in evidence_items:
            context_blocks.append(f"--- Source: {ev.source_title} ({ev.source_url}) ---\n{ev.excerpt}\n")

        context_text = "\n".join(context_blocks)

        return ResearchResult(
            topic=topic,
            queries=queries,
            evidence=evidence_items,
            citations=citations,
            context_text=context_text,
            total_chars=accumulated_chars,
            degraded=degraded,
        )

    # ── Composite: search + fetch (Quick or Deep research) ────────────────────

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
                    {"title": ev.source_title, "url": ev.source_url, "content": ev.excerpt}
                    for ev in res.evidence
                ],
                "context_text": res.context_text,
                "citations": res.citations,
                "provider": "serper",
                "degraded": res.degraded,
            }

        # Quick Research: 1 query, 5 results, top 2 pages with evidence excerpts
        n = max_results or settings.WEB_SEARCH_MAX_RESULTS
        cleaned_queries = optimize_queries(query, max_queries=1)
        primary_q = cleaned_queries[0] if cleaned_queries else query

        search_resp = await self.search(primary_q, category=category, max_results=n)
        if not search_resp.results and category != "all":
            search_resp = await self.search(primary_q, category="all", max_results=n)

        citations = []
        for r in search_resp.results[:5]:
            label = (r.title[:60] + "...") if len(r.title) > 60 else r.title
            citations.append(f"• [{label}]({r.url})")

        fetched_pages = []
        fetch_urls_list = [r.url for r in search_resp.results[:fetch_top_n] if r.url]
        if fetch_urls_list:
            fetch_results = await self.fetch_many(
                fetch_urls_list,
                max_chars_per_page=max_chars_per_page,
            )
            for idx, fr in enumerate(fetch_results):
                sr = search_resp.results[idx] if idx < len(search_resp.results) else None
                title = sr.title if sr else fr.url
                if fr.success and len(fr.content.strip()) >= 20:
                    excerpt = extract_evidence_excerpt(fr.content, query, max_chars=max_chars_per_page)
                    fetched_pages.append({
                        "title": title,
                        "url": fr.url,
                        "content": excerpt,
                    })
                elif sr and sr.snippet:
                    # Degradation to snippet on single-page fetch failure
                    fetched_pages.append({
                        "title": title,
                        "url": fr.url,
                        "content": sr.snippet,
                    })

        context_blocks = []
        if fetched_pages:
            context_blocks.append("### 📑 Full-Page Web Research Context:")
            for p in fetched_pages:
                context_blocks.append(f"--- Source: {p['title']} ({p['url']}) ---\n{p['content']}\n")
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
        }


# Module-level singleton
search_service = SearchService()
