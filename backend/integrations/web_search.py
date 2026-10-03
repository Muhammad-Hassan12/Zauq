"""Compatibility facade for Zauq Web Search.

In Zauq v4, all retrieval, scraping, and crawling logic is consolidated in
the backend.search subsystem (Serper provider, in-process TTL cache, safe fetcher).

This module preserves the legacy WebSearchEngine interface and signatures so that
older utility scripts and callers continue to work without modification, while
delegating all network actions to the unified SearchService.
"""

from __future__ import annotations
import logging
import urllib.parse
from typing import List, Dict, Any, Optional

from backend.search.fetcher import is_safe_public_url  # noqa: F401
from backend.search.service import (
    search_service,
    optimize_queries,
    should_search,
    extract_urls as svc_extract_urls,
)

logger = logging.getLogger("zauq.web_search")


class WebSearchEngine:
    """Universal Web Search and URL Content Reader for Zauq.

    Compatibility facade for Zauq v4: delegates all searches, URL fetches,
    and deep roaming to backend.search.service (Serper + Jina/safe HTTP + TTL cache).
    """

    def __init__(self) -> None:
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

    async def search_duckduckgo(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """Deprecated in v4: Delegates to the unified Serper-backed SearchService.

        Maintains backward compatibility with callers expecting:
        [{"title": ..., "url": ..., "snippet": ...}]
        """
        logger.debug(f"Legacy search_duckduckgo called for '{query}'; delegating to SearchService.")
        resp = await search_service.search(query=query, max_results=max_results)
        return [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
            }
            for r in resp.results
        ]

    async def fetch_url_content(self, target_url: str, max_chars: int = 8000) -> str:
        """Fetches and extracts clean readable markdown text from a webpage using the unified fetcher.

        Strict SSRF validation is enforced before any outbound HTTP request.
        """
        res = await search_service.fetch(target_url, max_chars=max_chars)
        if res.success:
            return res.content
        return f"[Failed to fetch webpage content: {res.error}]"

    def apply_category_filter(self, query: str, category: str = "all") -> str:
        """Appends domain-specific filters to search query based on category."""
        category = (category or "all").lower().strip()
        cleaned_q = query.strip()

        if category == "github":
            return f"site:github.com {cleaned_q}"
        elif category == "arxiv":
            return f"site:arxiv.org {cleaned_q}"
        elif category == "docs":
            return f"(site:docs.python.org OR site:developer.mozilla.org OR site:fastapi.tiangolo.com OR site:devdocs.io) {cleaned_q}"
        elif category == "wikipedia":
            return f"site:wikipedia.org {cleaned_q}"
        elif category == "news":
            return f"(site:news.ycombinator.com OR site:reuters.com OR site:techcrunch.com) {cleaned_q}"
        return cleaned_q

    def optimize_search_queries(self, raw_query: str, max_queries: int = 3) -> List[str]:
        """Cleans conversational filler and decomposes complex queries into targeted search queries."""
        return optimize_queries(raw_query, max_queries=max_queries)

    async def deep_search_and_roam(
        self,
        query: str,
        max_results: int = 5,
        roam_top_n: int = 2,
        category: str = "all",
    ) -> Dict[str, Any]:
        """Autonomous Deep Web Roaming Engine:

        Delegates to the unified SearchService (Serper + Jina/safe HTTP + in-process caching).
        """
        return await search_service.search_and_fetch(
            query=query,
            max_results=max_results,
            fetch_top_n=roam_top_n,
            category=category,
        )

    def extract_urls(self, text: str) -> List[str]:
        """Extracts all http/https URLs from a text string."""
        return svc_extract_urls(text)

    def should_search_web(self, query: str) -> bool:
        """Intelligent heuristic check if a user query requires live web search."""
        return should_search(query)


web_search_engine = WebSearchEngine()
