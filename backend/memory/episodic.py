import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
from backend.memory.db import db_helper
from backend.memory.embeddings import embedding_client
from backend.models.router import model_router

logger = logging.getLogger("zauq.episodic")

EXTRACTION_SYSTEM_PROMPT = """You are an episodic memory extraction agent.
Analyze the following conversation transcript and extract any notable personal facts, preferences, background details, technical stack, or project context stated by the user.
Output strictly valid JSON with the format:
{
  "facts": [
    {
      "category": "personal | technical | preference | project",
      "fact": "Description of the fact",
      "confidence": 0.9,
      "importance": 0.8
    }
  ]
}
Guidelines:
- "confidence" (0.0-1.0): how certain you are this fact is accurate based on what the user said
- "importance" (0.0-1.0): how useful/memorable this fact is for future conversations (personal identity, core technical stack, strong preferences = high; passing mentions = low)
- Only extract facts explicitly stated by the user, not inferred from the assistant
- Prefer specific facts over vague observations
If no notable facts are found, return {"facts": []}.
"""

# Contradiction signal keywords — if a new fact mentions these relative to an existing one
_NEGATION_SIGNALS = [
    "no longer", "stopped", "switched from", "don't use", "doesn't use",
    "not using", "gave up", "moved away from", "replaced", "instead of",
    "used to", "previously", "formerly", "not anymore"
]

def _has_contradiction_signal(fact_text: str) -> bool:
    """Check if a fact text contains a contradiction/negation signal."""
    lower = fact_text.lower()
    return any(sig in lower for sig in _NEGATION_SIGNALS)


async def get_relevant_user_memories(
    user_id: str,
    query_text: str,
    limit: int = 6
) -> List[Dict[str, Any]]:
    """
    Retrieve semantically relevant user memories for a given query.

    Strategy:
    1. Generate embedding for the current query text
    2. Call match_user_memories RPC (similarity * importance_score ranking)
    3. Fall back to recency query if embeddings unavailable
    4. Reinforce accessed memories (increment access_count, update last_accessed_at)
    """
    if not db_helper.supabase:
        return []

    # Try semantic retrieval first
    try:
        query_embedding = await embedding_client.get_embedding(query_text)
        # Only use vector search if we got a real (non-zero) embedding
        if any(v != 0.0 for v in query_embedding):
            memories = await db_helper.search_user_memories_by_vector(
                user_id=user_id,
                query_embedding=query_embedding,
                threshold=0.55,   # Slightly looser threshold for retrieval context
                limit=limit
            )
            if memories:
                # Reinforce accessed memories asynchronously
                for mem in memories:
                    mid = mem.get("memory_id")
                    if mid:
                        asyncio.create_task(db_helper.reinforce_memory(mid))
                return memories
    except Exception as e:
        logger.debug(f"Vector memory retrieval fallback for user {user_id}: {e}")

    # Fallback: recency-based retrieval (handles users with no embeddings yet)
    return await db_helper.get_user_memories(user_id, limit=limit)


async def extract_and_store_user_memories(
    user_id: str,
    messages: List[Dict[str, str]],
    provider: str = "gemini",
    model_name: str = "gemini-2.5-flash"
):
    """
    Full vector-based episodic memory extraction pipeline:

    1. LLM extraction — extract facts with confidence + importance scores
    2. Embedding generation — compute 768-dim embedding per fact
    3. Deduplication — skip near-duplicates (cosine > 0.92); reinforce close matches (> 0.80)
    4. Contradiction detection — halve importance of contradicted existing memories
    5. Importance-aware storage — store embedding + importance_score
    6. Memory expiry — prune decayed memories below min threshold
    """
    if not messages or not db_helper.supabase:
        return

    transcript_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
    extraction_user_prompt = f"Transcript:\n{transcript_text}\n\nExtract facts for User ID: {user_id}"

    try:
        raw_output = await model_router.generate(
            messages=[{"role": "user", "content": extraction_user_prompt}],
            provider=provider,
            model_name=model_name,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.1
        )

        # Parse JSON output
        clean_json = raw_output.strip()
        if clean_json.startswith("```"):
            clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        data = json.loads(clean_json)
        facts = data.get("facts", [])

        if not facts:
            return

        # Prune expired memories before adding new ones (keep memory clean)
        asyncio.create_task(db_helper.delete_expired_memories(min_importance=0.15))

        for item in facts:
            fact_str = item.get("fact", "").strip()
            if not fact_str:
                continue

            category = item.get("category", "general")
            confidence = float(item.get("confidence", 1.0))
            importance = float(item.get("importance", 0.7))

            # Boost importance for high-signal categories
            if category in ("personal", "technical"):
                importance = min(1.0, importance + 0.1)

            # Clamp values to [0, 1]
            confidence = max(0.0, min(1.0, confidence))
            importance = max(0.0, min(1.0, importance))

            # --- Step 2: Generate embedding ---
            embedding = await embedding_client.get_embedding(fact_str)
            has_real_embedding = any(v != 0.0 for v in embedding)

            # --- Step 3 & 4: Deduplication + Contradiction Detection ---
            if has_real_embedding and db_helper.supabase:
                try:
                    # Search for similar existing memories (loose threshold for dedup check)
                    similar = await db_helper.search_user_memories_by_vector(
                        user_id=user_id,
                        query_embedding=embedding,
                        threshold=0.70,   # Catch both near-dups and potential contradictions
                        limit=3
                    )

                    skip_insert = False
                    for existing_mem in similar:
                        sim = existing_mem.get("similarity", 0.0)
                        existing_id = existing_mem.get("memory_id")

                        if sim >= 0.92:
                            # Near-duplicate: reinforce existing, skip new insert
                            logger.debug("Memory deduplication skipped a near-duplicate.")
                            if existing_id:
                                asyncio.create_task(db_helper.reinforce_memory(existing_id))
                            skip_insert = True
                            break

                        elif sim >= 0.80:
                            # Close match: could be an update — reinforce, but still insert
                            if existing_id:
                                asyncio.create_task(db_helper.reinforce_memory(existing_id))

                        # --- Contradiction Detection ---
                        if sim >= 0.70 and _has_contradiction_signal(fact_str):
                            # New fact contradicts an existing one — demote the old memory
                            logger.info(
                                f"Contradiction detected for user {user_id}: "
                                f"existing memory {existing_id} was demoted"
                            )
                            if existing_id:
                                asyncio.create_task(db_helper.halve_memory_importance(existing_id))
                            # Tag the new fact as a correction
                            category = f"contradiction:{category}"

                    if skip_insert:
                        continue

                except Exception as dedup_err:
                    logger.debug(f"Dedup/contradiction check skipped: {dedup_err}")

            # --- Step 5: Store with embedding + importance ---
            await db_helper.add_user_memory(
                user_id=user_id,
                fact_content=fact_str,
                category=category,
                embedding=embedding if has_real_embedding else None,
                confidence_score=confidence,
                importance_score=importance
            )
            logger.info("Memory stored for user %s category=%s", user_id, category)

    except Exception as e:
        logger.warning(f"Memory extraction failed for user {user_id}: {e}")
