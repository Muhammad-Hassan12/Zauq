"""
Native web tools: web.search and web.fetch.

Registered with tool_registry at import time.
Each handler is a thin async wrapper that delegates to SearchService.

Called by ToolExecutor during the Phase 4 agent loop.
Also called directly from chat.py enrichment when AGENT_RUNTIME_ENABLED=False
(Phase 2 transition period — both paths work).
"""
from __future__ import annotations
import logging
from backend.tools.base import ToolSpec
from backend.tools.registry import tool_registry
from backend.search.service import search_service

logger = logging.getLogger("zauq.tools.native.web")

# ── web.search ────────────────────────────────────────────────────────────────

_WEB_SEARCH_SPEC = ToolSpec(
    name="web.search",
    description=(
        "Search the live web for current information, news, code repositories, "
        "research papers, or documentation. Returns up to 5 ranked results "
        "with title, URL, and snippet. "
        "Supported categories: all, github, arxiv, docs, wikipedia, news."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query string.",
            },
            "category": {
                "type": "string",
                "enum": ["all", "github", "arxiv", "docs", "wikipedia", "news"],
                "description": "Domain filter. Default: 'all'.",
            },
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (1-10). Default: 5.",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    },
    source="native",
    risk="read",
    timeout_seconds=12.0,
    enabled=True,
)


async def _web_search_handler(args: dict) -> dict:
    query = args.get("query", "").strip()
    if not query:
        return {"error": "query is required"}
    category = args.get("category", "all")
    max_results = int(args.get("max_results", 5))
    max_results = max(1, min(max_results, 10))

    resp = await search_service.search(query, category=category, max_results=max_results)

    return {
        "query": resp.query,
        "category": resp.category,
        "provider": resp.provider,
        "from_cache": resp.from_cache,
        "results": [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
                "position": r.position,
            }
            for r in resp.results
        ],
    }


# ── web.fetch ─────────────────────────────────────────────────────────────────

_WEB_FETCH_SPEC = ToolSpec(
    name="web.fetch",
    description=(
        "Fetch and extract readable text content from a public URL. "
        "Uses Jina Reader with a direct-HTTP fallback. "
        "Enforces SSRF protection — private/internal addresses are blocked. "
        "Returns the page content as text, truncated to max_chars."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The full https:// URL to fetch.",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters to return (default: 8000, max: 12000).",
                "minimum": 100,
                "maximum": 12000,
            },
        },
        "required": ["url"],
    },
    source="native",
    risk="read",
    timeout_seconds=15.0,
    enabled=True,
)


async def _web_fetch_handler(args: dict) -> dict:
    url = args.get("url", "").strip()
    if not url:
        return {"error": "url is required"}
    max_chars = int(args.get("max_chars", 8000))
    max_chars = max(100, min(max_chars, 12000))

    result = await search_service.fetch(url, max_chars=max_chars)

    return {
        "url": result.url,
        "success": result.success,
        "content": result.content,
        "error": result.error,
        "method": result.method,
        "char_count": result.char_count,
    }


# ── Registration ──────────────────────────────────────────────────────────────

def register_web_tools() -> None:
    """
    Register web.search and web.fetch with the global tool_registry.
    Called once at application startup (from backend/main.py lifespan in Phase 4).
    Safe to call multiple times — raises ValueError on duplicate registration.
    """
    if tool_registry.get("web.search") is None:
        tool_registry.register(_WEB_SEARCH_SPEC, _web_search_handler)
        logger.info("Registered tool: web.search")
    if tool_registry.get("web.fetch") is None:
        tool_registry.register(_WEB_FETCH_SPEC, _web_fetch_handler)
        logger.info("Registered tool: web.fetch")
