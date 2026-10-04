from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Literal, Callable, Awaitable

# Canonical risk level type
RiskLevel = Literal["read", "write", "destructive", "privileged"]


@dataclass
class ToolSpec:
    """
    Describes a registerable tool.

    All tools — native or MCP-adapted — are stored in ToolRegistry as ToolSpec.
    The handler callable is kept separately in the registry, not in this object,
    so ToolSpec can be safely serialized/compared.
    """
    name: str
    description: str
    input_schema: dict[str, Any]
    source: str = "native"
    risk: RiskLevel = "read"
    timeout_seconds: float = 15.0
    enabled: bool = True
    server_id: str | None = None
    original_tool_name: str | None = None
    allowed_guild_ids: list[str] | None = None
    selection_keywords: list[str] = field(default_factory=list)
    _handler: Callable[[dict], Awaitable[Any]] | None = field(
        default=None, repr=False, compare=False
    )


@dataclass
class ToolResult:
    """
    Normalized output of a single tool execution.

    Returned for execution failures; request cancellation propagates.
    """
    tool_name: str
    success: bool
    content: Any = None
    error: str | None = None
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_text(self, max_chars: int = 12000) -> str:
        """
        Serialize content to a string.
        Truncates at max_chars with a clear notice.
        Returns a structured error string on failure.
        """
        if not self.success:
            return f"[Tool Error: {self.error}]"
        text = str(self.content) if self.content is not None else ""
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n[...truncated at {max_chars} chars]"
        return text
