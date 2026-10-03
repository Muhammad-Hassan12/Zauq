from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""
    id: str               # provider-issued call ID
    name: str             # canonical tool name (e.g. "web.search")
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallBatch:
    """A set of tool calls in one model turn (usually 1, rarely parallel)."""
    calls: list[ToolCall] = field(default_factory=list)


@dataclass
class ToolResultMessage:
    """Result fed back into the model after tool execution."""
    tool_call_id: str
    tool_name: str
    content: str          # serialized result (truncated if needed)
    is_error: bool = False

    @property
    def name(self) -> str:
        return self.tool_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "name": self.tool_name,
            "content": self.content,
            "is_error": self.is_error,
        }


@dataclass
class AgentModelTurn:
    """Normalized output of one model step in the agent loop."""
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def is_final_answer(self) -> bool:
        return bool(self.text) and not self.tool_calls
