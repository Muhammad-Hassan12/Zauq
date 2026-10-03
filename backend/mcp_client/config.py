"""Configuration loader and environment-variable interpolator for MCP servers."""

from __future__ import annotations
import os
import re
import json
import logging
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.mcp_client.models import MCPConfigFile, MCPServerConfig

logger = logging.getLogger("zauq.mcp.config")

# Pattern for ${VAR} or ${VAR:-default} or $VAR
_ENV_VAR_PATTERN = re.compile(r"\$(?:\{([A-Za-z0-9_]+)(?::-([^}]*))?\}|([A-Za-z0-9_]+))")


def interpolate_env_vars(val: Any) -> Any:
    """Recursively replace environment variable references in strings, dicts, and lists."""
    if isinstance(val, str):
        def _replace(match: re.Match) -> str:
            var_name = match.group(1) or match.group(3)
            default_val = match.group(2) if match.group(2) is not None else ""
            return os.getenv(var_name, default_val)
        return _ENV_VAR_PATTERN.sub(_replace, val)
    elif isinstance(val, dict):
        return {k: interpolate_env_vars(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [interpolate_env_vars(item) for item in val]
    return val


def load_mcp_config(config_path: str | Path | None = None) -> MCPConfigFile:
    """Load, validate, and interpolate MCP server configuration from JSON file.

    Returns an empty MCPConfigFile if the file is missing or invalid.
    Enforces MCP_MAX_SERVERS.
    """
    path_to_load = Path(config_path or settings.MCP_CONFIG_PATH)

    if not path_to_load.is_file():
        logger.debug(f"MCP config file not found at '{path_to_load}'. Returning empty config.")
        return MCPConfigFile(servers=[])

    try:
        with open(path_to_load, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read MCP config from '{path_to_load}': {e}")
        return MCPConfigFile(servers=[])

    # Interpolate environment variables
    interpolated = interpolate_env_vars(raw_data)

    try:
        config = MCPConfigFile.model_validate(interpolated)
    except Exception as e:
        logger.error(f"Invalid MCP configuration structure in '{path_to_load}': {e}")
        return MCPConfigFile(servers=[])

    # Enforce MCP_MAX_SERVERS
    max_servers = getattr(settings, "MCP_MAX_SERVERS", 5)
    if len(config.servers) > max_servers:
        logger.warning(
            f"Configured MCP servers ({len(config.servers)}) exceeds MCP_MAX_SERVERS ({max_servers}). "
            f"Truncating to first {max_servers} servers."
        )
        config.servers = config.servers[:max_servers]

    # Validate per-server transport requirements
    valid_servers: list[MCPServerConfig] = []
    for s in config.servers:
        if s.transport == "streamable_http" and not s.url:
            logger.warning(f"Server '{s.id}' skipped: transport is 'streamable_http' but no 'url' provided.")
            continue
        if s.transport == "stdio" and not s.command:
            logger.warning(f"Server '{s.id}' skipped: transport is 'stdio' but no 'command' provided.")
            continue
        valid_servers.append(s)

    config.servers = valid_servers
    return config
