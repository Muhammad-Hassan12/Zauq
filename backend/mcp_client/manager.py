"""MCP Manager for Zauq v4.

Manages connections to external Model Context Protocol (MCP) servers,
discovers and caches tools, registers them into ToolRegistry, and provides
lifecycle management and failure isolation.
"""

from __future__ import annotations
import asyncio
import logging
import time
from contextlib import AsyncExitStack
from typing import Any, Callable, Awaitable

from backend.config import settings
from backend.tools.registry import ToolRegistry, tool_registry
from backend.tools.base import ToolSpec
from backend.mcp_client.models import MCPServerConfig, MCPServerStatus, MCPConfigFile
from backend.mcp_client.config import load_mcp_config
from backend.mcp_client.adapter import mcp_tool_to_spec

logger = logging.getLogger("zauq.mcp.manager")


class ServerConnection:
    """Encapsulates the active connection, session, and exit stack for a single MCP server."""

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.stack: AsyncExitStack | None = None
        self.session: Any = None
        self.status = MCPServerStatus(
            id=config.id,
            connected=False,
            tools=0,
            transport=config.transport,
        )
        self.cached_tools: list[ToolSpec] = []
        self._reconnect_task: asyncio.Task | None = None
        self._backoff_seconds: float = 5.0
        self._max_backoff: float = 60.0
        self.consecutive_failures: int = 0
        self.max_consecutive_failures: int = 5


_mcp_call_semaphore: Optional[asyncio.Semaphore] = None


def _get_mcp_call_semaphore() -> asyncio.Semaphore:
    global _mcp_call_semaphore
    if _mcp_call_semaphore is None:
        max_conc = getattr(settings, "MCP_MAX_CONCURRENCY", 4)
        _mcp_call_semaphore = asyncio.Semaphore(max_conc)
    return _mcp_call_semaphore


class MCPManager:
    """Central manager for external MCP server connections and tools.

    Guarantees:
    - Zero overhead when MCP_ENABLED is False
    - Disconnected servers never break normal chat operations
    - Server failure isolation: failure in one server does not impact others
    - Reconnects with bounded backoff
    - Clean disconnection on shutdown
    - In-memory tool discovery cache
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        config: MCPConfigFile | None = None,
    ) -> None:
        self.registry = registry if registry is not None else tool_registry
        self.config = config
        self.connections: dict[str, ServerConnection] = {}
        self._running: bool = False
        self._lock = asyncio.Lock()

    def is_enabled(self) -> bool:
        """Check if MCP client features are enabled in settings."""
        return bool(getattr(settings, "MCP_ENABLED", False))

    async def start(self) -> None:
        """Start the MCP manager during FastAPI lifespan."""
        if not self.is_enabled():
            logger.info("MCP client is disabled (MCP_ENABLED=false). Skipping startup.")
            return

        async with self._lock:
            if self._running:
                return
            self._running = True

            # Load configuration if not injected
            if self.config is None:
                self.config = load_mcp_config()

            logger.info(f"Starting MCP Manager with {len(self.config.servers)} configured server(s)...")

            # Initialize connections
            for s_cfg in self.config.servers:
                self.connections[s_cfg.id] = ServerConnection(s_cfg)

            # Connect all enabled servers concurrently with failure isolation
            connect_tasks = [
                self._connect_server(conn)
                for conn in self.connections.values()
                if conn.config.enabled
            ]
            if connect_tasks:
                await asyncio.gather(*connect_tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Cleanly disconnect all MCP servers and unregister their tools."""
        async with self._lock:
            self._running = False
            disconnect_tasks = [
                self._disconnect_server(conn)
                for conn in self.connections.values()
            ]
            if disconnect_tasks:
                await asyncio.gather(*disconnect_tasks, return_exceptions=True)
            self.connections.clear()
            logger.info("MCP Manager stopped.")

    async def _connect_server(self, conn: ServerConnection) -> bool:
        """Connect to an individual MCP server with failure isolation."""
        conn.status.connected = False
        conn.status.error = None

        if not conn.config.enabled:
            logger.debug(f"MCP server '{conn.config.id}' is disabled. Skipping.")
            return False

        try:
            from mcp.client.session import ClientSession

            stack = AsyncExitStack()

            if conn.config.transport == "streamable_http":
                from mcp.client.streamable_http import streamable_http_client
                if not conn.config.url:
                    raise ValueError(f"Server '{conn.config.id}' missing required URL for streamable_http.")
                
                # Streamable HTTP client context
                streams = await stack.enter_async_context(
                    streamable_http_client(conn.config.url)
                )
                session = await stack.enter_async_context(
                    ClientSession(streams[0], streams[1])
                )

            elif conn.config.transport == "stdio":
                from mcp.client.stdio import stdio_client, StdioServerParameters
                if not conn.config.command:
                    raise ValueError(f"Server '{conn.config.id}' missing required command for stdio.")

                params = StdioServerParameters(
                    command=conn.config.command,
                    args=conn.config.args,
                    env=conn.config.env or None,
                )
                streams = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(
                    ClientSession(streams[0], streams[1])
                )

            else:
                raise ValueError(f"Unsupported transport: {conn.config.transport}")

            # Initialize protocol session
            await session.initialize()

            conn.stack = stack
            conn.session = session
            conn.status.connected = True
            conn.status.last_connected_at = time.time()
            conn._backoff_seconds = 5.0  # Reset backoff on success

            # Discover tools and register them
            await self._discover_and_register_tools(conn)
            conn.consecutive_failures = 0
            conn._backoff_seconds = 5.0
            logger.info(
                f"Successfully connected to MCP server '{conn.config.id}' "
                f"({conn.config.transport}) with {conn.status.tools} tool(s)."
            )
            return True

        except Exception as e:
            conn.status.connected = False
            conn.status.error = str(e)
            conn.consecutive_failures += 1
            logger.warning(f"Failed to connect to MCP server '{conn.config.id}' (attempt {conn.consecutive_failures}): {e}")
            if conn.stack:
                try:
                    await conn.stack.aclose()
                except Exception:
                    pass
                conn.stack = None
                conn.session = None

            # Circuit breaker: pause reconnect loop on repeated failures to prevent retry storms
            if conn.consecutive_failures >= conn.max_consecutive_failures:
                if conn._reconnect_task and not conn._reconnect_task.done():
                    conn._reconnect_task.cancel()
                    conn._reconnect_task = None
                logger.warning(
                    f"MCP server '{conn.config.id}' exceeded max consecutive failures ({conn.consecutive_failures}). "
                    "Pausing background reconnection until explicit refresh to protect host."
                )
            elif self._running and conn.config.enabled:
                self._schedule_reconnect(conn)

            return False

    def _schedule_reconnect(self, conn: ServerConnection) -> None:
        """Schedule a background reconnection with bounded exponential backoff."""
        if conn._reconnect_task and not conn._reconnect_task.done():
            return

        async def _reconnect_loop():
            await asyncio.sleep(conn._backoff_seconds)
            conn._backoff_seconds = min(conn._backoff_seconds * 1.5, conn._max_backoff)
            if self._running and not conn.status.connected:
                logger.info(f"Attempting reconnection to MCP server '{conn.config.id}'...")
                await self._connect_server(conn)

        conn._reconnect_task = asyncio.create_task(_reconnect_loop())

    async def _discover_and_register_tools(self, conn: ServerConnection) -> None:
        """Discover tools once, normalize, cache in memory, and register into ToolRegistry."""
        if not conn.session or not conn.status.connected:
            return

        try:
            tool_list_res = await conn.session.list_tools()
            tools_raw = getattr(tool_list_res, "tools", [])

            # Clear previously registered tools for this server
            self.registry.unregister_by_server(conn.config.id)
            conn.cached_tools.clear()

            async def _make_call_tool(tool_name: str, args: dict[str, Any]) -> Any:
                if not conn.session or not conn.status.connected:
                    raise RuntimeError(f"MCP server '{conn.config.id}' is currently disconnected.")
                sem = _get_mcp_call_semaphore()
                timeout = float(getattr(settings, "MCP_DEFAULT_TIMEOUT_SECONDS", 20.0))
                async with sem:
                    return await asyncio.wait_for(
                        conn.session.call_tool(tool_name, arguments=args),
                        timeout=timeout,
                    )

            # Adapt and register each tool
            for t in tools_raw:
                try:
                    spec = mcp_tool_to_spec(t, conn.config, _make_call_tool)
                    handler = spec._handler
                    if handler is not None:
                        self.registry.register(spec, handler)
                        conn.cached_tools.append(spec)
                except Exception as ex:
                    logger.warning(f"Failed to register MCP tool '{getattr(t, 'name', t)}': {ex}")

            conn.status.tools = len(conn.cached_tools)

        except Exception as e:
            logger.error(f"Error discovering tools from MCP server '{conn.config.id}': {e}")
            conn.status.tools = 0

    async def _disconnect_server(self, conn: ServerConnection) -> None:
        """Cleanly close connection and unregister tools for a server."""
        if conn._reconnect_task and not conn._reconnect_task.done():
            conn._reconnect_task.cancel()

        # Unregister tools from ToolRegistry
        self.registry.unregister_by_server(conn.config.id)
        conn.cached_tools.clear()

        if conn.stack:
            try:
                await conn.stack.aclose()
            except Exception as e:
                logger.debug(f"Error closing exit stack for '{conn.config.id}': {e}")
            conn.stack = None

        conn.session = None
        conn.status.connected = False
        conn.status.tools = 0

    async def refresh_server(self, server_id: str) -> bool:
        """Operator-requested refresh for a connected server's tools."""
        conn = self.connections.get(server_id)
        if not conn:
            return False

        conn.consecutive_failures = 0
        conn._backoff_seconds = 5.0
        if not conn.status.connected:
            return await self._connect_server(conn)

        await self._discover_and_register_tools(conn)
        return True

    def get_status(self) -> dict[str, Any]:
        """Return safe health status representation without credentials."""
        servers_summary = [
            conn.status.to_safe_summary()
            for conn in self.connections.values()
        ]
        return {
            "enabled": self.is_enabled(),
            "servers": servers_summary,
        }

    def list_cached_tools(self, server_id: str | None = None) -> list[ToolSpec]:
        """Return list of cached ToolSpec objects for one or all MCP servers."""
        if server_id:
            conn = self.connections.get(server_id)
            return list(conn.cached_tools) if conn else []
        
        all_tools = []
        for conn in self.connections.values():
            all_tools.extend(conn.cached_tools)
        return all_tools


# Global singleton instance
mcp_manager = MCPManager()
