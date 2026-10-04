import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from backend.memory.db import db_helper
from backend.search.cache import search_cache

logger = logging.getLogger("zauq.metrics")

# In-memory metrics fallback buffer (bounded at 1000 items)
IN_MEMORY_LOGS: List[Dict[str, Any]] = []

def estimate_provider_cost(provider, model_name, input_tokens, output_tokens):
    """Use operator-supplied per-model USD rates per million tokens.

    Unknown usage or pricing is unknown cost, never a fabricated zero bill.
    """
    import json
    import math
    from backend.config import settings
    if input_tokens is None or output_tokens is None:
        return None
    try:
        rates = json.loads(settings.MODEL_PRICING_JSON).get(f"{provider}:{model_name}")
        if not rates or len(rates) != 2 or any(not isinstance(r, (int,float)) or isinstance(r, bool) or not math.isfinite(r) or r < 0 for r in rates):
            return None
        return round((input_tokens*rates[0] + output_tokens*rates[1])/1_000_000, 8)
    except (ValueError, TypeError, AttributeError):
        return None


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
    provider_usage: Optional[list] = None,
    status: str = "ok",
):
    """
    Logs an API request metric with Phase 11 observability telemetry.
    Note: Full user prompts and tool secrets are never recorded.
    """
    if estimated_provider_cost is None and (input_tokens or output_tokens):
        estimated_provider_cost = estimate_provider_cost(provider, model_name, input_tokens, output_tokens)

    if provider_usage:
        costs = [estimate_provider_cost(r['provider'],r['model'],r['input_tokens'],r['output_tokens']) if not r.get('cache_read_input_tokens') and not r.get('cache_creation_input_tokens') else None for r in provider_usage]
        estimated_provider_cost = sum(costs) if all(c is not None for c in costs) else None
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
        "provider_usage": provider_usage or [],
        "status": status,
    }
    IN_MEMORY_LOGS.append(entry)

    # Keep memory buffer under 1000 items
    if len(IN_MEMORY_LOGS) > 1000:
        IN_MEMORY_LOGS.pop(0)

    if db_helper.supabase:
        try:
            payload = {key:value for key,value in entry.items() if key not in ('timestamp','estimated_provider_cost')}
            payload['estimated_cost_usd'] = estimated_provider_cost
            await asyncio.to_thread(lambda: db_helper.supabase.table("request_logs").insert(payload).execute())
        except Exception as e:
            logger.warning(f"Could not persist request log to Supabase: {e}")


async def get_metrics_summary(guild_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns aggregated metrics: request count, latency, provider breakdown,
    v4 tool telemetry, token metrics, cost estimates, and cache stats.
    """
    cache_info = search_cache.stats
    if db_helper.supabase:
        try:
            response = await asyncio.to_thread(lambda: db_helper.supabase.rpc('v4_metrics_summary', {'requested_guild': None if guild_id in (None,'global') else guild_id}).execute())
            if isinstance(response.data, dict):
                return {**response.data, 'source':'database', 'cache_stats':cache_info}
        except Exception:
            logger.warning('Durable metrics summary unavailable; reporting bounded local buffer.')


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
            "window": "last 1000 requests in this process",
            "unknown_cost_requests": 0,
            "unknown_usage_requests": 0,
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
    unknown_cost_requests = 0
    unknown_usage_requests = 0

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
        unknown_cost_requests += int(log.get("estimated_provider_cost") is None)
        unknown_usage_requests += int(log.get("input_tokens") is None or log.get("output_tokens") is None)

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
        "total_estimated_cost_usd": None if unknown_cost_requests else round(total_cost, 6),
        "known_estimated_cost_usd": round(total_cost, 6),
        "unknown_cost_requests": unknown_cost_requests,
        "unknown_usage_requests": unknown_usage_requests,
        "window": "last 1000 requests in this process",
        "cache_stats": cache_info,
        "source": "in_memory",
    }
