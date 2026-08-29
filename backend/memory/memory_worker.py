"""
Memory Decay Worker — runs as a background asyncio task every 24 hours.

Responsibilities:
  1. decay_old_memories: reduce importance_score by 5% for memories not
     accessed in the past 30 days (slow forgetting curve)
  2. delete_expired_memories: prune memories whose importance has decayed
     below 0.15 (effectively forgotten)

This keeps user memory lean, relevant, and fresh without ever touching
memories that are being actively accessed (reinforcement resets the clock).
"""

import asyncio
import logging
from backend.memory.db import db_helper

logger = logging.getLogger("zauq.memory_worker")

_DECAY_INTERVAL_SECONDS = 60 * 60 * 24   # 24 hours
_DAYS_BEFORE_DECAY = 30                   # memories untouched for 30 days start decaying
_DECAY_RATE = 0.05                        # 5% importance reduction per cycle
_MIN_IMPORTANCE_THRESHOLD = 0.15          # memories below this are pruned


async def run_memory_maintenance_cycle() -> None:
    """Execute one full decay + expiry cycle and log results."""
    try:
        decayed = await db_helper.decay_old_memories(
            days_threshold=_DAYS_BEFORE_DECAY,
            decay_rate=_DECAY_RATE
        )
        pruned = await db_helper.delete_expired_memories(
            min_importance=_MIN_IMPORTANCE_THRESHOLD
        )
        logger.info(
            f"[MemoryWorker] Cycle complete — "
            f"decayed: {decayed} memories, pruned: {pruned} expired memories."
        )
    except Exception as e:
        logger.error(f"[MemoryWorker] Maintenance cycle error: {e}")


async def start_memory_decay_worker() -> None:
    """
    Long-running background task. Runs the first cycle immediately on startup
    (to clean up any stale memories from before this feature), then repeats
    every 24 hours.
    """
    logger.info("[MemoryWorker] Starting memory decay worker...")
    # First run on startup
    await run_memory_maintenance_cycle()
    # Then loop every 24h
    while True:
        await asyncio.sleep(_DECAY_INTERVAL_SECONDS)
        await run_memory_maintenance_cycle()
