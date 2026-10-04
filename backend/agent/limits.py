from __future__ import annotations
from dataclasses import dataclass

# Default step budgets can be configured up to the global hard ceiling (but can probably cause issues if increased too much)
# Model output cannot change any budget; code repair has its own hard ceiling.
NORMAL_MAX_TOOL_STEPS: int = 4
DEEP_MAX_TOOL_STEPS: int = 6
GLOBAL_MAX_TOOL_STEPS: int = 8
MAX_CODE_REPAIR_ATTEMPTS: int = 1


@dataclass
class AgentBudget:
    """
    Per-request resource budget consumed during the agent loop.
    Instantiated by the agent runtime before each run.
    Never modified by LLM output.
    """
    max_tool_steps: int = NORMAL_MAX_TOOL_STEPS
    max_search_calls: int = 2
    max_pages_fetched: int = 3
    max_sandbox_calls: int = 1
    max_mcp_calls: int = 4
    max_tool_failures: int = 2

    # Runtime counters... incremented by the runtime, never by the LLM
    tool_steps_used: int = 0
    search_calls_used: int = 0
    pages_fetched_used: int = 0
    page_fetch_attempts: int = 0
    sandbox_calls_used: int = 0
    mcp_calls_used: int = 0
    tool_failures_used: int = 0

    def is_exhausted(self) -> bool:
        """True when the tool step limit has been reached."""
        return self.tool_steps_used >= self.max_tool_steps or self.tool_failures_used >= self.max_tool_failures

    def can_search(self) -> bool:
        return self.search_calls_used < self.max_search_calls

    def can_fetch_page(self) -> bool:
        return self.page_fetch_attempts < self.max_pages_fetched

    def can_use_sandbox(self) -> bool:
        return self.sandbox_calls_used < self.max_sandbox_calls

    def can_use_mcp(self) -> bool:
        return self.mcp_calls_used < self.max_mcp_calls
