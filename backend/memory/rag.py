import asyncio
import logging
from typing import List, Dict, Any
from backend.memory.db import db_helper
from backend.memory.embeddings import embedding_client

logger = logging.getLogger("zauq.rag")

async def add_server_lore(guild_id: str, source_type: str, content: str) -> Dict[str, Any]:
    if not db_helper.supabase:
        return {}

    embedding = await embedding_client.get_embedding(content)
    payload = {
        "guild_id": guild_id,
        "source_type": source_type,
        "content": content,
        "embedding": embedding
    }
    res = await asyncio.to_thread(lambda: db_helper.supabase.table("server_lore").insert(payload).execute())
    return res.data[0] if res.data else payload

async def search_server_lore(guild_id: str, query_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
    if not db_helper.supabase:
        return []

    try:
        query_embedding = await embedding_client.get_embedding(query_text)
        # Try RPC vector similarity search first
        try:
            rpc_res = db_helper.supabase.rpc(
                "match_server_lore",
                {
                    "query_embedding": query_embedding,
                    "match_guild_id": guild_id,
                    "match_threshold": 0.1,
                    "match_count": top_k
                }
            ).execute()
            if rpc_res.data:
                return rpc_res.data
        except Exception as rpc_err:
            logger.info(f"RPC match_server_lore fallback to table query: {rpc_err}")

        # Fallback to direct table query by guild_id
        res = db_helper.supabase.table("server_lore") \
            .select("lore_id, guild_id, source_type, content") \
            .eq("guild_id", guild_id) \
            .limit(top_k) \
            .execute()
        return res.data or []
    except Exception as e:
        logger.warning(f"Failed to query server lore: {e}")
        return []

async def get_lore_context_prompt(guild_id: str, query_text: str) -> str:
    if not guild_id:
        return ""

    lore_items = await search_server_lore(guild_id, query_text, top_k=3)
    if not lore_items:
        return ""

    formatted_lore = "\n".join([f"- [{item.get('source_type', 'lore').upper()}]: {item['content']}" for item in lore_items])
    return f"\n\n[Server Lore & Grounded Knowledge Base]:\n{formatted_lore}"
