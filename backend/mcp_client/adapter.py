"""Adapter to convert MCP tools into Zauq ToolSpec objects and execution handlers."""

from __future__ import annotations
import logging
from typing import Any, Callable, Awaitable
from backend.tools.base import ToolSpec, RiskLevel
from backend.mcp_client.models import MCPServerConfig

logger = logging.getLogger("zauq.mcp.adapter")

_DISALLOWED_UNNAMESPACED_NAMES = frozenset({
    "search", "get", "read", "write", "post", "put", "delete",
    "fetch", "execute", "run", "query", "find", "list",
})


def make_canonical_name(
    server_id: str,
    original_tool_name: str,
    namespace_prefix: str | None = None,
) -> str:
    """Generate a canonical namespaced tool name for Zauq.

    Format:
    - If namespace_prefix is provided: `<namespace_prefix>.<original_tool_name>`
    - Default: `mcp.<server_id>.<original_tool_name>`

    Disallows un-namespaced ambiguous names like 'search', 'get', 'read'.
    """
    clean_tool_name = original_tool_name.strip()
    clean_prefix = namespace_prefix.strip(".") if namespace_prefix else ""
    clean_server_id = server_id.strip(".") if server_id else ""

    if clean_prefix:
        canonical = f"{clean_prefix}.{clean_tool_name}"
    elif clean_server_id:
        canonical = f"mcp.{clean_server_id}.{clean_tool_name}"
    else:
        canonical = clean_tool_name

    # Verify no bare ambiguous names: must have at least 2 non-empty parts
    parts = [p for p in canonical.split(".") if p]
    if len(parts) < 2:
        raise ValueError(
            f"MCP tool '{original_tool_name}' produced ambiguous canonical name '{canonical}'. "
            "Tools must have at least one namespace prefix."
        )

    return canonical


def format_mcp_result(result: Any) -> Any:
    """Format and normalize the output from an MCP call_tool result."""
    if result is None:
        return ""

    # If result is an MCP CallToolResult object (or similar duck-typed object)
    is_error = getattr(result, "is_error", False)
    content = getattr(result, "content", None)
    structured = getattr(result, "structured_content", None)

    if structured is not None:
        if is_error:
            raise RuntimeError(f"MCP tool error: {structured}")
        return structured

    if content is not None and isinstance(content, list):
        text_parts = []
        for item in content:
            if hasattr(item, "text"):
                text_parts.append(str(item.text))
            elif isinstance(item, dict) and "text" in item:
                text_parts.append(str(item["text"]))
            elif hasattr(item, "data"):
                text_parts.append(str(item.data))
            else:
                text_parts.append(str(item))
        joined = "\n".join(text_parts)
        if is_error:
            raise RuntimeError(f"MCP tool reported error: {joined}")
        return joined

    if isinstance(result, dict):
        if result.get("is_error"):
            raise RuntimeError(f"MCP tool reported error: {result.get('content') or result}")
        return result

    return str(result)


def create_mcp_handler(
    call_tool_fn: Callable[[str, dict[str, Any]], Awaitable[Any]],
    original_tool_name: str,
) -> Callable[[dict[str, Any]], Awaitable[Any]]:
    """Return an async callable that executes the tool via MCP session."""
    async def _handler(arguments: dict[str, Any]) -> Any:
        try:
            raw_result = await call_tool_fn(original_tool_name, arguments or {})
            return format_mcp_result(raw_result)
        except Exception as e:
            logger.warning(f"Error executing MCP tool '{original_tool_name}': {e}")
            raise

    return _handler


def mcp_tool_to_spec(
    tool: Any,
    server_config: MCPServerConfig,
    call_tool_fn: Callable[[str, dict[str, Any]], Awaitable[Any]],
) -> ToolSpec:
    """Convert an MCP Tool definition to a Zauq ToolSpec."""
    # Extract name
    if hasattr(tool, "name"):
        original_name = tool.name
    elif isinstance(tool, dict):
        original_name = tool.get("name", "")
    else:
        original_name = str(tool)

    # Extract description
    if hasattr(tool, "description") and tool.description:
        description = tool.description
    elif isinstance(tool, dict) and tool.get("description"):
        description = tool["description"]
    else:
        description = f"MCP tool '{original_name}' from server '{server_config.id}'"

    # Extract input_schema
    input_schema: dict[str, Any] = {}
    if hasattr(tool, "input_schema") and tool.input_schema:
        if isinstance(tool.input_schema, dict):
            input_schema = tool.input_schema
        elif hasattr(tool.input_schema, "model_dump"):
            input_schema = tool.input_schema.model_dump()
    elif isinstance(tool, dict) and "input_schema" in tool:
        input_schema = tool["input_schema"] or {}
    elif isinstance(tool, dict) and "inputSchema" in tool:
        input_schema = tool["inputSchema"] or {}

    if not input_schema or not isinstance(input_schema, dict):
        input_schema = {"type": "object", "properties": {}}

    # Determine risk level
    # SECURITY INVARIANT: Check server overrides first, then default_risk
    tool_risk: RiskLevel = server_config.tool_risks.get(
        original_name,
        server_config.default_risk,
    )

    canonical_name = make_canonical_name(
        server_id=server_config.id,
        original_tool_name=original_name,
        namespace_prefix=server_config.namespace_prefix,
    )

    handler = create_mcp_handler(call_tool_fn, original_name)

    spec = ToolSpec(
        name=canonical_name,
        description=description,
        input_schema=input_schema,
        source="mcp",
        risk=tool_risk,
        timeout_seconds=server_config.timeout_seconds,
        enabled=server_config.enabled,
        server_id=server_config.id,
        original_tool_name=original_name,
        allowed_guild_ids=list(server_config.allowed_guild_ids) if server_config.allowed_guild_ids else None,
        _handler=handler,
    )

    return spec
