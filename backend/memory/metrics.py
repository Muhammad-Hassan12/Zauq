import time
import logging
from typing import Dict, Any, List, Optional
from backend.memory.db import db_helper

logger = logging.getLogger("zauq.metrics")

# In-memory metrics fallback buffer
IN_MEMORY_LOGS: List[Dict[str, Any]] = []

async def log_request_metric(
    guild_id: Optional[str],
    channel_id: str,
    user_id: Optional[str],
    tier: int,
    provider: str,
    model_name: str,
    response_time_ms: int
):
    """
    Logs an API request metric asynchronously to Supabase request_logs table
    with an in-memory buffer fallback.
    """
    entry = {
        "guild_id": guild_id or "dm",
        "channel_id": channel_id,
        "user_id": user_id or "anonymous",
        "tier": tier,
        "provider": provider,
        "model_name": model_name,
        "response_time_ms": response_time_ms,
        "timestamp": time.time()
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
                "response_time_ms": response_time_ms
            }
            await asyncio.to_thread(lambda: db_helper.supabase.table("request_logs").insert(payload).execute())
        except Exception as e:
            logger.warning(f"Could not persist request log to Supabase: {e}")

async def get_metrics_summary(guild_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns aggregated metrics: total request count, average latency, and provider breakdown.
    """
    if db_helper.supabase:
        try:
            query = db_helper.supabase.table("request_logs").select("*")
            if guild_id and guild_id != "global":
                query = query.eq("guild_id", guild_id)
            res = query.order("created_at", desc=True).limit(500).execute()
            data = res.data or []
            if data:
                total_reqs = len(data)
                avg_latency = sum(item.get("response_time_ms", 0) for item in data) / total_reqs
                provider_counts = {}
                for item in data:
                    prov = item.get("provider", "gemini").upper()
                    provider_counts[prov] = provider_counts.get(prov, 0) + 1

                return {
                    "total_requests": total_reqs,
                    "avg_latency_ms": round(avg_latency, 1),
                    "provider_breakdown": provider_counts,
                    "source": "supabase"
                }
        except Exception as e:
            logger.info(f"Supabase metrics fetch fallback: {e}")

    # In-memory buffer fallback
    filtered_logs = [log for log in IN_MEMORY_LOGS if not guild_id or guild_id == "global" or log.get("guild_id") == guild_id]
    total_reqs = len(filtered_logs)
    if total_reqs == 0:
        return {
            "total_requests": 0,
            "avg_latency_ms": 0,
            "provider_breakdown": {"GEMINI": 0},
            "source": "in_memory"
        }

    avg_latency = sum(log["response_time_ms"] for log in filtered_logs) / total_reqs
    provider_counts = {}
    for log in filtered_logs:
        prov = log.get("provider", "gemini").upper()
        provider_counts[prov] = provider_counts.get(prov, 0) + 1

    return {
        "total_requests": total_reqs,
        "avg_latency_ms": round(avg_latency, 1),
        "provider_breakdown": provider_counts,
        "source": "in_memory"
    }
