"""Tool Schema Normalization and Formatting across Model Providers.

Translates Zauq ToolSpec schemas into provider-native tool declarations for
Gemini, Anthropic, and OpenAI-compatible providers (Qwen, DeepSeek, DigitalOcean).
"""

from __future__ import annotations
from typing import Any, Dict, List, Union
from backend.tools.base import ToolSpec
from backend.tools.aliases import canonical_to_alias, alias_to_canonical


def _clean_schema_for_gemini(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Cleans JSON schema to ensure compatibility with Gemini's function declaration parser.
    
    Removes unsupported keys like $schema, title, and handles type definitions.
    """
    if not isinstance(schema, dict):
        return schema

    cleaned: Dict[str, Any] = {}
    for k, v in schema.items():
        if k in ["$schema", "title", "$id"]:
            continue
        if k == "type" and isinstance(v, str):
            cleaned["type"] = v.upper()
        elif k == "properties" and isinstance(v, dict):
            cleaned["properties"] = {
                prop_k: _clean_schema_for_gemini(prop_v)
                for prop_k, prop_v in v.items()
            }
        elif k == "items" and isinstance(v, dict):
            cleaned["items"] = _clean_schema_for_gemini(v)
        else:
            cleaned[k] = v

    if "type" not in cleaned:
        cleaned["type"] = "OBJECT"
    return cleaned


def to_gemini_tools(specs: List[Union[ToolSpec, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Converts a list of ToolSpecs or dict specs into Gemini functionDeclarations format."""
    declarations = []
    for spec in specs:
        if isinstance(spec, ToolSpec):
            name = canonical_to_alias(spec.name)
            desc = spec.description
            schema = spec.input_schema
        else:
            raw_name = spec.get("name", "")
            name = canonical_to_alias(raw_name) if "." in raw_name else raw_name
            desc = spec.get("description", "")
            schema = spec.get("input_schema") or spec.get("parameters") or {}

        declarations.append({
            "name": name,
            "description": desc,
            "parameters": _clean_schema_for_gemini(schema),
        })

    return [{"functionDeclarations": declarations}] if declarations else []


def to_anthropic_tools(specs: List[Union[ToolSpec, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Converts a list of ToolSpecs into Anthropic Claude tool definitions."""
    tools = []
    for spec in specs:
        if isinstance(spec, ToolSpec):
            name = canonical_to_alias(spec.name)
            desc = spec.description
            schema = spec.input_schema
        else:
            raw_name = spec.get("name", "")
            name = canonical_to_alias(raw_name) if "." in raw_name else raw_name
            desc = spec.get("description", "")
            schema = spec.get("input_schema") or spec.get("parameters") or {"type": "object"}

        tools.append({
            "name": name,
            "description": desc,
            "input_schema": schema,
        })
    return tools


def to_openai_tools(specs: List[Union[ToolSpec, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Converts a list of ToolSpecs into OpenAI-compatible tools definitions."""
    tools = []
    for spec in specs:
        if isinstance(spec, ToolSpec):
            name = canonical_to_alias(spec.name)
            desc = spec.description
            schema = spec.input_schema
        else:
            raw_name = spec.get("name", "")
            name = canonical_to_alias(raw_name) if "." in raw_name else raw_name
            desc = spec.get("description", "")
            schema = spec.get("input_schema") or spec.get("parameters") or {"type": "object"}

        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": desc,
                "parameters": schema,
            }
        })
    return tools


def normalize_tool_call_name(call_name: str) -> str:
    """Converts provider alias back to canonical dot-separated tool name."""
    return alias_to_canonical(call_name)
