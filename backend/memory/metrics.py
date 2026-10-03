import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from backend.memory.db import db_helper
from backend.search.cache import search_cache

logger = logging.getLogger("zauq.metrics")

# In-memory metrics fallback buffer (bounded at 1000 items)
IN_MEMORY_LOGS: List[Dict[str, Any]] = []

# Metadata-driven cost rates per 1,000,000 tokens [prompt_rate_usd, completion_rate_usd]
_PROVIDER_PRICING_PER_MILLION: Dict[str, tuple[float, float]] = {
    "gemini": (0.075, 0.30),
    "anthropic": (3.00, 15.00),
    "qwen": (0.14, 0.28),
    "deepseek": (0.14, 0.28),
    "digitalocean": (0.15, 0.60),
    "ollama": (0.0, 0.0),
    "kaggle": (0.0, 0.0),
}


def estimate_provider_cost(
    provider: str,
    model_name: str,
    input_tokens: Optional[int],
    output_tokens: Optional[int],
) -> Optional[float]:
    """Estimates LLM provider invocation cost based on token counts."""
    if input_tokens is None and output_tokens is None:
        return None

    prov = provider.lower().strip()
    prompt_rate, comp_rate = _PROVIDER_PRICING_PER_MILLION.get(prov, (0.15, 0.60))

    in_cost = ((input_tokens or 0) / 1_000_000.0) * prompt_rate
    out_cost = ((output_tokens or 0) / 1_000_000.0) * comp_rate
    return round(in_cost + out_cost, 6)


async def log_request_metric(
    guild_id: Optional[str],
    channel_id: str,
    user_id: Optional[str],
    tier: int,
    provider: str,
    model_name: str,
    response_time_ms: int,
    *,
    tool_steps: int = 0,
    search_calls: int = 0,
    pages_fetched: int = 0,
    sandbox_calls: int = 0,
    mcp_calls: int = 0,
    tool_failures: int = 0,
    agent_duration_ms: Optional[int] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    estimated_provider_cost: Optional[float] = None,
    request_id: Optional[str] = None,
    agent_run_id: Optional[str] = None,
):
    """
    Logs an API request metric with Phase 11 observability telemetry.
    Note: Full user prompts and tool secrets are never recorded.
    """
    if estimated_provider_cost is None and (input_tokens or output_tokens):
        estimated_provider_cost = estimate_provider_cost(provider, model_name, input_tokens, output_tokens)

    entry = {
        "guild_id": guild_id or "dm",
        "channel_id": channel_id,
        "user_id": user_id or "anonymous",
        "tier": tier,
        "provider": provider,
        "model_name": model_name,
        "response_time_ms": response_time_ms,
        "tool_steps": tool_steps,
        "search_calls": search_calls,
        "pages_fetched": pages_fetched,
        "sandbox_calls": sandbox_calls,
        "mcp_calls": mcp_calls,
        "tool_failures": tool_failures,
        "agent_duration_ms": agent_duration_ms if agent_duration_ms is not None else response_time_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_provider_cost": estimated_provider_cost,
        "request_id": request_id,
        "agent_run_id": agent_run_id,
        "timestamp": time.time(),
    }
    IN_MEMORY_LOGS.append(entry)

    # Keep memory buffer under 1000 items
    if len(IN_MEMORY_LOGS) > 1000:
        IN_MEMORY_LOGS.pop(0)

    if db_helper.supabase:
        try:
            payload = {
                "guild_id": guild_id or "dm",
                "channel_id": channel_id,
                "user_id": user_id or "anonymous",
                "tier": tier,
                "provider": provider,
                "model_name": model_name,
                "response_time_ms": response_time_ms,
            }
            await asyncio.to_thread(lambda: db_helper.supabase.table("request_logs").insert(payload).execute())
        except Exception as e:
            logger.warning(f"Could not persist request log to Supabase: {e}")


async def get_metrics_summary(guild_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns aggregated metrics: request count, latency, provider breakdown,
    v4 tool telemetry, token metrics, cost estimates, and cache stats.
    """
    cache_info = search_cache.stats

    # Filter in-memory logs
    filtered_logs = [
        log for log in IN_MEMORY_LOGS
        if not guild_id or guild_id == "global" or log.get("guild_id") == guild_id
    ]
    total_reqs = len(filtered_logs)
    if total_reqs == 0:
        return {
            "total_requests": 0,
            "avg_latency_ms": 0,
            "provider_breakdown": {"GEMINI": 0},
            "total_tool_steps": 0,
            "total_search_calls": 0,
            "total_pages_fetched": 0,
            "total_sandbox_calls": 0,
            "total_mcp_calls": 0,
            "total_tool_failures": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_estimated_cost_usd": 0.0,
            "cache_stats": cache_info,
            "source": "in_memory",
        }

    avg_latency = sum(log["response_time_ms"] for log in filtered_logs) / total_reqs
    provider_counts: Dict[str, int] = {}
    total_tool_steps = 0
    total_search_calls = 0
    total_pages_fetched = 0
    total_sandbox_calls = 0
    total_mcp_calls = 0
    total_tool_failures = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0.0

    for log in filtered_logs:
        prov = log.get("provider", "gemini").upper()
        provider_counts[prov] = provider_counts.get(prov, 0) + 1
        total_tool_steps += log.get("tool_steps", 0)
        total_search_calls += log.get("search_calls", 0)
        total_pages_fetched += log.get("pages_fetched", 0)
        total_sandbox_calls += log.get("sandbox_calls", 0)
        total_mcp_calls += log.get("mcp_calls", 0)
        total_tool_failures += log.get("tool_failures", 0)
        total_input_tokens += log.get("input_tokens") or 0
        total_output_tokens += log.get("output_tokens") or 0
        total_cost += log.get("estimated_provider_cost") or 0.0

    return {
        "total_requests": total_reqs,
        "avg_latency_ms": round(avg_latency, 1),
        "provider_breakdown": provider_counts,
        "total_tool_steps": total_tool_steps,
        "total_search_calls": total_search_calls,
        "total_pages_fetched": total_pages_fetched,
        "total_sandbox_calls": total_sandbox_calls,
        "total_mcp_calls": total_mcp_calls,
        "total_tool_failures": total_tool_failures,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_estimated_cost_usd": round(total_cost, 6),
        "cache_stats": cache_info,
        "source": "in_memory",
    }
