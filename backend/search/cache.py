from __future__ import annotations
import time
import hashlib
import logging
from collections import OrderedDict
from typing import Any
from backend.config import settings

logger = logging.getLogger("zauq.search.cache")

# Category-specific TTLs in seconds
_CATEGORY_TTL: dict[str, int] = {
    "news": 90,         
    "all": 300,         
    "github": 300,
    "arxiv": 1800,      
    "docs": 900,        
    "wikipedia": 900,
}
_DEFAULT_TTL = 300


def _make_cache_key(
    provider: str,
    query: str,
    category: str,
    max_results: int,
) -> str:
    """Deterministic cache key that covers all parameters that affect results."""
    raw = f"{provider}|{query.lower().strip()}|{category}|{max_results}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class SearchCache:
    """
    Bounded in-process TTL cache for search results.

    No Redis required. Designed for a single-process FastAPI backend.
    Uses an OrderedDict so eviction (LRU-style) is O(1).

    Thread safety: asyncio is single-threaded; no lock needed.
    """

    def __init__(self, max_entries: int = 256) -> None:
        self._max_entries = max_entries
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, key: str, ttl: int) -> Any | None:
        """Return cached value if present and not expired, else None."""
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return None
        stored_at, value = entry
        if time.monotonic() - stored_at > ttl:
            del self._store[key]
            self._misses += 1
            return None
        # Move to end (most-recently-used)
        self._store.move_to_end(key)
        self._hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        """Store a value. Evicts oldest entry if capacity is exceeded."""
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.monotonic(), value)
        while len(self._store) > self._max_entries:
            self._store.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    @property
    def stats(self) -> dict[str, int]:
        return {
            "entries": len(self._store),
            "hits": self._hits,
            "misses": self._misses,
        }

    def ttl_for_category(self, category: str) -> int:
        base = max(0, settings.WEB_SEARCH_CACHE_TTL_SECONDS)
        return int(_CATEGORY_TTL.get(category, _DEFAULT_TTL) * base / _DEFAULT_TTL)

    def make_key(
        self,
        provider: str,
        query: str,
        category: str,
        max_results: int,
    ) -> str:
        return _make_cache_key(provider, query, category, max_results)


# Module-level singleton
search_cache = SearchCache(max_entries=256)
