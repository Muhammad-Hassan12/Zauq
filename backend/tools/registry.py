from __future__ import annotations
import logging
from jsonschema import Draft202012Validator
from typing import Callable, Awaitable, Any
from backend.tools.base import ToolSpec, RiskLevel
from backend.tools.aliases import AliasMap

logger = logging.getLogger("zauq.tools.registry")

_RISK_ORDER: list[str] = ["read", "write", "destructive", "privileged"]


class ToolRegistry:
    """
    Central registry of all available tools.

    Responsibilities:
    - Register native tools and (later) MCP-adapted tools
    - Reject duplicate canonical names
    - Generate and resolve provider-safe aliases
    - Filter tools by risk level or enabled state
    - Expose tool definitions in a format suitable for LLM provider payloads
    - Never execute tools itself (that is ToolExecutor's job)

    The module-level singleton `tool_registry` should be used throughout Zauq.
    """

    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[[dict], Awaitable[Any]]] = {}
        self.aliases = AliasMap()

    def register(
        self,
        spec: ToolSpec,
        handler: Callable[[dict], Awaitable[Any]],
    ) -> None:
        """
        Register a tool with its async handler.

        Raises ValueError if the canonical name is already registered.
        """
        if spec.name in self._specs:
            raise ValueError(
                f"Tool '{spec.name}' is already registered. "
                "Each tool must have a unique canonical name."
            )
        Draft202012Validator.check_schema(spec.input_schema)
        def check_refs(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in ('$ref', '$dynamicRef', '$recursiveRef') and (not isinstance(child, str) or not child.startswith('#')):
                        raise ValueError('Remote schema references are prohibited')
                    check_refs(child)
            elif isinstance(value, list):
                for child in value:
                    check_refs(child)
        check_refs(spec.input_schema)
        if spec.risk not in _RISK_ORDER or spec.timeout_seconds <= 0:
            raise ValueError('Invalid risk or timeout')
        self.aliases.register(spec.name)
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler
        logger.debug(f"Registered tool: '{spec.name}' (risk={spec.risk}, source={spec.source})")

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool by canonical name or alias.
        Returns True if removed, False if not found.
        """
        try:
            canonical = self.aliases.resolve(name)
        except KeyError:
            return False
        self._specs.pop(canonical, None)
        self._handlers.pop(canonical, None)
        self.aliases.unregister(canonical)
        logger.debug(f"Unregistered tool: '{canonical}'")
        return True

    def unregister_by_server(self, server_id: str) -> list[str]:
        """
        Unregister all tools belonging to a given server_id.
        Returns a list of unregistered canonical tool names.
        """
        removed = []
        to_remove = [
            canonical for canonical, spec in self._specs.items()
            if spec.server_id == server_id
        ]
        for canonical in to_remove:
            self.unregister(canonical)
            removed.append(canonical)
        return removed

    def get(self, name: str) -> ToolSpec | None:
        """
        Look up a ToolSpec by canonical name or provider alias.
        Returns None if not found.
        """
        try:
            canonical = self.aliases.resolve(name)
        except KeyError:
            return None
        return self._specs.get(canonical)

    def get_handler(self, name: str) -> Callable[[dict], Awaitable[Any]] | None:
        """
        Return the async handler for a tool by canonical name or alias.
        Returns None if not found.
        """
        try:
            canonical = self.aliases.resolve(name)
        except KeyError:
            return None
        return self._handlers.get(canonical)

    def list_tools(
        self,
        enabled_only: bool = True,
        max_risk: RiskLevel | None = None,
    ) -> list[ToolSpec]:
        """
        Return a filtered list of registered ToolSpec objects.

        Args:
            enabled_only: Skip disabled tools when True (default).
            max_risk: Only include tools with risk <= max_risk in severity order
                      ("read" < "write" < "destructive" < "privileged").
        """
        tools = list(self._specs.values())
        if enabled_only:
            tools = [t for t in tools if t.enabled]
        if max_risk is not None:
            ceiling = _RISK_ORDER.index(max_risk)
            tools = [t for t in tools if _RISK_ORDER.index(t.risk) <= ceiling]
        return tools

    def get_specs_for_provider(
        self,
        enabled_only: bool = True,
        max_risk: RiskLevel | None = None,
    ) -> list[dict]:
        """
        Return tool definitions with provider-safe aliased names.
        Suitable for inclusion in LLM API payloads (e.g. Gemini function
        declarations, Anthropic tool definitions, OpenAI tool schemas).
        """
        specs = []
        for spec in self.list_tools(enabled_only=enabled_only, max_risk=max_risk):
            alias = self.aliases.get_alias(spec.name)
            specs.append({
                "name": alias,
                "description": spec.description,
                "input_schema": spec.input_schema,
            })
        return specs

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None


# Module-level singleton... import and use this everywhere in Zauq
tool_registry = ToolRegistry()
