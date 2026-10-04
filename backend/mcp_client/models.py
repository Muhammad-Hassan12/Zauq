from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
from backend.tools.base import RiskLevel


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server connection."""
    id: str = Field(min_length=1, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')
    enabled: bool = True
    transport: Literal["streamable_http", "stdio"] = "streamable_http"
    url: str | None = None
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    allowed_guild_ids: list[str] = Field(default_factory=list)
    allow_global_access: bool = False
    allowed_tools: list[str] = Field(default_factory=list)
    selection_keywords: list[str] = Field(default_factory=list)
    default_risk: RiskLevel = 'write'
    timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    namespace_prefix: str | None = None
    tool_risks: dict[str, RiskLevel] = Field(default_factory=dict)


class MCPConfigFile(BaseModel):
    """Root configuration structure in mcp_servers.json."""
    servers: list[MCPServerConfig] = Field(default_factory=list)


class MCPServerStatus(BaseModel):
    """Runtime connection status and health for an MCP server."""
    id: str
    connected: bool = False
    tools: int = 0
    error: str | None = None
    transport: str = "streamable_http"
    last_connected_at: float | None = None

    def to_safe_summary(self) -> dict[str, Any]:
        """Return public safe summary for health/status responses without sensitive info."""
        res: dict[str, Any] = {
            "id": self.id,
            "connected": self.connected,
            "tools": self.tools,
        }
        if self.error:
            from backend.security.sanitizer import sanitize_secrets
            res["error"] = sanitize_secrets(self.error)[:200]
        return res


class MCPHealthResponse(BaseModel):
    """Schema returned by GET /api/mcp/status."""
    enabled: bool
    servers: list[dict[str, Any]]
