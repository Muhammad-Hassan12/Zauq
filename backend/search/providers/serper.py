from __future__ import annotations
import logging
import httpx
from backend.search.models import SearchResult, SearchResponse
from backend.config import settings

logger = logging.getLogger("zauq.search.providers.serper")

# Category → Serper endpoint / query modifier map
_CATEGORY_CONFIG: dict[str, dict] = {
    "all":       {"endpoint": "/search",    "query_prefix": ""},
    "github":    {"endpoint": "/search",    "query_prefix": "site:github.com "},
    "arxiv":     {"endpoint": "/search",    "query_prefix": "site:arxiv.org "},
    "docs":      {"endpoint": "/search",    "query_prefix": ""},
    "wikipedia": {"endpoint": "/search",    "query_prefix": "site:wikipedia.org "},
    "news":      {"endpoint": "/news",      "query_prefix": ""},
}

class SerperProvider:
    """
    Serper.dev Google Search API provider.

    Implements normalized search compatible with SearchService.
    Falls back cleanly when SERPER_API_KEY is not set.
    """

    BASE_URL = "https://google.serper.dev"

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key if api_key is not None else settings.SERPER_API_KEY

    @property
    def available(self) -> bool:
        """True when an API key is configured."""
        return bool(self._api_key)

    def _build_query(self, query: str, category: str) -> str:
        """Apply category-specific query prefix/modification."""
        category = (category or "all").lower().strip()
        cfg = _CATEGORY_CONFIG.get(category, _CATEGORY_CONFIG["all"])
        prefix = cfg["query_prefix"]
        q = query.strip()
        if category == "docs":
            return f"{q} official documentation"
        return f"{prefix}{q}"

    def _parse_results(
        self,
        data: dict,
        query: str,
        category: str,
        max_results: int,
    ) -> SearchResponse:
        """
        Parse the Serper JSON payload into a normalized SearchResponse.
        Handles both /search (organic) and /news (news items) endpoints.
        """
        results: list[SearchResult] = []

        # /news endpoint uses 'news' key; /search uses 'organic'
        items = data.get("organic", data.get("news", []))

        for idx, item in enumerate(items[:max_results]):
            url = item.get("link", "")
            if not url:
                continue
            results.append(SearchResult(
                title=item.get("title", "Untitled"),
                url=url,
                snippet=item.get("snippet", ""),
                position=idx + 1,
                source="serper",
                published_at=item.get("date"),
            ))

        return SearchResponse(
            query=query,
            results=results,
            category=category,
            provider="serper",
        )

    async def search(
        self,
        query: str,
        category: str = "all",
        max_results: int | None = None,
    ) -> SearchResponse:
        """
        Execute a Serper search call.

        Returns explicit unavailability when the key is absent; no hidden fallback.
        """
        n = max_results or settings.WEB_SEARCH_MAX_RESULTS
        effective_query = self._build_query(query, category)

        if not self.available:
            logger.warning("SerperProvider: no API key — skipping search")
            return SearchResponse(query=query, results=[], category=category, provider="serper", error='Search unavailable: SERPER_API_KEY is not configured', search_calls=0)

        cat = (category or "all").lower().strip()
        cfg = _CATEGORY_CONFIG.get(cat, _CATEGORY_CONFIG["all"])
        endpoint = self.BASE_URL + cfg["endpoint"]

        payload = {
            "q": effective_query,
            "num": min(n, 10),      # Serper caps at 10 per call
        }
        headers = {
            "X-API-KEY": self._api_key,
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(endpoint, json=payload, headers=headers)
                if res.status_code != 200:
                    logger.warning(
                        f"Serper returned HTTP {res.status_code}"
                    )
                    return SearchResponse(query=query, results=[], category=category, provider="serper", error=f'Search provider returned HTTP {res.status_code}')

                data = res.json()
                response = self._parse_results(data, query, category, n)
                logger.info(
                    f"Serper search ok: category={category} "
                    f"results={len(response.results)}"
                )
                return response

        except Exception as exc:
            logger.warning('Serper request failed (%s)', type(exc).__name__)
            return SearchResponse(query=query, results=[], category=category, provider="serper", error='Search provider request failed')


# Module-level singleton
serper = SerperProvider()
