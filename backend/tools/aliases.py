from __future__ import annotations


def canonical_to_alias(name: str) -> str:
    """
    Convert a canonical tool name to a provider-safe alias.
    'web.search' -> 'web__search'
    Dots are replaced with double-underscores because not every LLM provider
    accepts dots in function/tool names.
    """
    return name.replace(".", "__")


def alias_to_canonical(alias: str) -> str:
    """
    Reverse of canonical_to_alias.
    'web__search' -> 'web.search'
    """
    return alias.replace("__", ".")


class AliasMap:
    """
    Bidirectional, deterministic mapping between canonical tool names and
    provider-safe aliases.

    - canonical: "web.search", "github.search_code"
    - alias:     "web__search", "github__search_code"

    Re-registering the same canonical name is idempotent and returns the
    existing alias. Alias collisions (two different canonicals producing the
    same alias) raise ValueError.
    """

    def __init__(self) -> None:
        self._c2a: dict[str, str] = {}   # canonical -> alias
        self._a2c: dict[str, str] = {}   # alias -> canonical

    def register(self, canonical: str) -> str:
        """
        Register a canonical name and return its alias.
        Idempotent — safe to call multiple times with the same name.
        """
        if canonical in self._c2a:
            return self._c2a[canonical]
        alias = canonical_to_alias(canonical)
        if alias in self._a2c:
            raise ValueError(
                f"Alias collision: '{alias}' already maps to "
                f"'{self._a2c[alias]}'. Cannot register '{canonical}'."
            )
        self._c2a[canonical] = alias
        self._a2c[alias] = canonical
        return alias

    def get_alias(self, canonical: str) -> str | None:
        """Return the alias for a canonical name, or None if not registered."""
        return self._c2a.get(canonical)

    def get_canonical(self, alias: str) -> str | None:
        """Return the canonical name for an alias, or None if not registered."""
        return self._a2c.get(alias)

    def resolve(self, name: str) -> str:
        """
        Resolve either a canonical name or alias to canonical form.
        Raises KeyError if the name is not registered.
        """
        if name in self._c2a:
            return name
        if name in self._a2c:
            return self._a2c[name]
        raise KeyError(f"Unknown tool name or alias: '{name}'")

    def all_aliases(self) -> dict[str, str]:
        """Return a copy of the canonical -> alias mapping."""
        return dict(self._c2a)
