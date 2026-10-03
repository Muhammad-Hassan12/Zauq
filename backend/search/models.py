from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class SearchResult:
    """
    Normalized search result.
    All providers (Serper, future providers) produce this format.
    """
    title: str
    url: str
    snippet: str
    position: int = 0
    source: str = "serper"
    published_at: str | None = None

    def to_text(self, include_url: bool = True) -> str:
        """One-line text summary suitable for LLM context injection."""
        url_part = f" ({self.url})" if include_url else ""
        return f"{self.title}{url_part}: {self.snippet}"


@dataclass
class SearchResponse:
    """
    Aggregated results from one search call.
    """
    query: str
    results: list[SearchResult] = field(default_factory=list)
    category: str = "all"
    provider: str = "serper"
    from_cache: bool = False

    @property
    def urls(self) -> list[str]:
        return [r.url for r in self.results if r.url]

    def to_context_block(self, max_results: int = 5) -> str:
        """
        Format results as a compact text block for LLM context injection.
        """
        if not self.results:
            return ""
        lines = [f"### 🌐 Web Search Results for: {self.query}"]
        for r in self.results[:max_results]:
            lines.append(f"• **{r.title}** ({r.url})\n  {r.snippet}")
        return "\n".join(lines)


@dataclass
class FetchResult:
    """
    Result of fetching and extracting content from a single URL.
    """
    url: str
    success: bool
    content: str = ""
    error: str | None = None
    method: str = "jina"     # "jina" | "direct" | "blocked"
    char_count: int = 0

    def __post_init__(self) -> None:
        self.char_count = len(self.content)


@dataclass
class EvidenceItem:
    """Structured evidence excerpt extracted from a retrieved web source (Phase 10)."""
    claim: str
    source_url: str
    source_title: str
    excerpt: str


@dataclass
class ResearchResult:
    """Structured output of a bounded deep research cycle (Phase 10)."""
    topic: str
    queries: list[str]
    evidence: list[EvidenceItem] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    context_text: str = ""
    total_chars: int = 0
    degraded: bool = False
    from_cache: bool = False
