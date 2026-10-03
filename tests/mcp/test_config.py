"""Tests for MCP configuration loading, environment variable interpolation, and validation."""

import os
import json
import pytest
from pathlib import Path
from backend.mcp_client.config import interpolate_env_vars, load_mcp_config
from backend.mcp_client.models import MCPServerConfig, MCPConfigFile


def test_interpolate_env_vars(monkeypatch):
    monkeypatch.setenv("TEST_SECRET_TOKEN", "token_xyz123")
    monkeypatch.setenv("TEST_HOST", "mcp.example.local")

    raw = {
        "url": "https://${TEST_HOST}/mcp",
        "auth": "Bearer ${TEST_SECRET_TOKEN}",
        "default": "${UNSET_VAR:-fallback_value}",
        "plain": "no_interpolation",
        "nested": {
            "items": ["prefix_${TEST_HOST}_suffix"]
        }
    }

    result = interpolate_env_vars(raw)

    assert result["url"] == "https://mcp.example.local/mcp"
    assert result["auth"] == "Bearer token_xyz123"
    assert result["default"] == "fallback_value"
    assert result["plain"] == "no_interpolation"
    assert result["nested"]["items"] == ["prefix_mcp.example.local_suffix"]


def test_load_mcp_config_missing_file():
    cfg = load_mcp_config("/non/existent/mcp_servers.json")
    assert isinstance(cfg, MCPConfigFile)
    assert len(cfg.servers) == 0


def test_load_mcp_config_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "gh_pat_999")

    config_data = {
        "servers": [
            {
                "id": "github",
                "enabled": True,
                "transport": "streamable_http",
                "url": "https://mcp.github.com/v1",
                "headers": {"Authorization": "Bearer ${GH_TOKEN}"},
                "allowed_guild_ids": ["123456789"],
                "default_risk": "read",
            },
            {
                "id": "local-docs",
                "enabled": False,
                "transport": "stdio",
                "command": "python",
                "args": ["server.py"],
                "default_risk": "read",
            }
        ]
    }

    config_file = tmp_path / "mcp_servers.json"
    config_file.write_text(json.dumps(config_data), encoding="utf-8")

    cfg = load_mcp_config(config_file)
    assert len(cfg.servers) == 2
    assert cfg.servers[0].id == "github"
    assert cfg.servers[0].headers["Authorization"] == "Bearer gh_pat_999"
    assert cfg.servers[1].id == "local-docs"


def test_load_mcp_config_invalid_transport_skipped(tmp_path):
    # streamable_http without url, stdio without command
    config_data = {
        "servers": [
            {
                "id": "bad-http",
                "transport": "streamable_http",
            },
            {
                "id": "bad-stdio",
                "transport": "stdio",
            },
            {
                "id": "good-http",
                "transport": "streamable_http",
                "url": "https://good.mcp/v1",
            }
        ]
    }
    config_file = tmp_path / "mcp_servers.json"
    config_file.write_text(json.dumps(config_data), encoding="utf-8")

    cfg = load_mcp_config(config_file)
    assert len(cfg.servers) == 1
    assert cfg.servers[0].id == "good-http"


def test_load_mcp_config_max_servers_enforcement(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.config.settings.MCP_MAX_SERVERS", 2)

    config_data = {
        "servers": [
            {"id": f"srv_{i}", "transport": "streamable_http", "url": f"https://srv{i}.mcp"}
            for i in range(5)
        ]
    }
    config_file = tmp_path / "mcp_servers.json"
    config_file.write_text(json.dumps(config_data), encoding="utf-8")

    cfg = load_mcp_config(config_file)
    assert len(cfg.servers) == 2
    assert [s.id for s in cfg.servers] == ["srv_0", "srv_1"]
