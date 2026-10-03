"""Zauq v4 MCP Client Layer package.

Provides client-side integration with Model Context Protocol (MCP) servers,
safe tool discovery, namespace isolation, and health monitoring.
"""

from backend.mcp_client.manager import MCPManager, mcp_manager
from backend.mcp_client.models import MCPServerConfig, MCPConfigFile, MCPServerStatus
from backend.mcp_client.adapter import mcp_tool_to_spec, make_canonical_name
from backend.mcp_client.config import load_mcp_config

__all__ = [
    "MCPManager",
    "mcp_manager",
    "MCPServerConfig",
    "MCPConfigFile",
    "MCPServerStatus",
    "mcp_tool_to_spec",
    "make_canonical_name",
    "load_mcp_config",
]
