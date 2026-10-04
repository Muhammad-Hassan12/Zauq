import logging
import math
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from backend.memory.embeddings import embedding_client

logger = logging.getLogger("zauq.context")

router = APIRouter(prefix="/api/context", tags=["Context Optimization"])

class CandidateMessage(BaseModel):
    role: str
    content: str

class ContextRankRequest(BaseModel):
    query: str
    candidates: List[CandidateMessage]
    top_k: int = 8

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot / (norm1 * norm2)

@router.post("/rank")
async def rank_context(req: ContextRankRequest):
    if not req.candidates:
        return {"ranked_messages": []}

    try:
        query_vec = await embedding_client.get_embedding(req.query)
        scored_messages = []

        for idx, msg in enumerate(req.candidates):
            msg_vec = await embedding_client.get_embedding(msg.content[:500])
            sim = cosine_similarity(query_vec, msg_vec)
            scored_messages.append((idx, sim, msg.model_dump()))

        scored_messages.sort(key=lambda x: x[1], reverse=True)
        top_candidates = scored_messages[:req.top_k]
        top_candidates.sort(key=lambda x: x[0])

        ranked = [item[2] for item in top_candidates]
        return {"ranked_messages": ranked}
    except Exception as e:
        logger.error(f"Context ranking error: {e}")
        raise HTTPException(status_code=500, detail="Context ranking computation failed.")
