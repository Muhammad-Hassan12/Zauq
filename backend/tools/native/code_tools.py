"""Native code execution tool: code.execute.

Registered with tool_registry at import time.
Invokes the hardened sandbox runner to execute code in isolated containers.
Subject to tool policy (risk="privileged", requires allow_code_exec=True).
"""

from __future__ import annotations
import logging
from typing import Any, Dict

from backend.tools.base import ToolSpec
from backend.tools.registry import tool_registry
from backend.sandbox.code_runner import execute_code
from backend.config import settings

logger = logging.getLogger("zauq.tools.native.code")

_CODE_EXECUTE_SPEC = ToolSpec(
    name="code.execute",
    description=(
        "Execute python, javascript, or bash code in an isolated, secure Docker sandbox. "
        "Returns stdout, stderr, exit_code, and execution duration. "
        "Supported languages: python, javascript, bash. Network access is disabled."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The complete runnable code script to execute.",
            },
            "language": {
                "type": "string",
                "enum": ["python", "javascript", "bash"],
                "description": "Programming language interpreter (default: python).",
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 8, max: 30).",
                "minimum": 1,
                "maximum": 30,
            },
        },
        "required": ["code"],
    },
    source="native",
    risk="privileged",
    timeout_seconds=30.0,
    enabled=True,
)


async def _code_execute_handler(args: Dict[str, Any]) -> Dict[str, Any]:
    code = args.get("code", "").strip()
    if not code:
        return {"error": "code is required"}

    lang = args.get("language", "python").lower()
    timeout = args.get("timeout")
    timeout_float = float(timeout) if timeout is not None else float(settings.SANDBOX_DEFAULT_TIMEOUT_SECONDS)

    res = await execute_code(code=code, language=lang, timeout=timeout_float)
    return res


# Register with tool_registry at module import time
try:
    tool_registry.register(_CODE_EXECUTE_SPEC, _code_execute_handler)
    logger.debug("Successfully registered native tool 'code.execute'")
except ValueError as e:
    logger.debug(f"code.execute already registered: {e}")
