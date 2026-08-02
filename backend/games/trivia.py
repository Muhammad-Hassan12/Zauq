import random
from typing import Dict, Any, List
from backend.memory.rag import search_server_lore

TECH_TRIVIA_BANK = [
    {
        "question": "What is the primary execution model of Python's GIL (Global Interpreter Lock)?",
        "options": [
            "Ensures only one thread executes Python bytecode at a time",
            "Compiles Python code directly to machine code",
            "Manages Docker container networking",
            "Locks files on disk to prevent concurrent writes"
        ],
        "correct_index": 0,
        "explanation": "The GIL is a mutex that protects access to Python objects, preventing multiple threads from executing Python bytecodes at once in CPython."
    },
    {
        "question": "What does HTTP status code 418 signify?",
        "options": [
            "Forbidden Access",
            "I'm a teapot (RFC 2324 / RFC 7168)",
            "Gateway Timeout",
            "Unprocessable Entity"
        ],
        "correct_index": 1,
        "explanation": "HTTP 418 I'm a teapot was defined in 1998 as an April Fools' joke in RFC 2324."
    },
    {
        "question": "Which data structure operates on a First-In, First-Out (FIFO) principle?",
        "options": [
            "Stack",
            "Queue",
            "Binary Tree",
            "Heap"
        ],
        "correct_index": 1,
        "explanation": "Queues process items in FIFO order, whereas Stacks operate on LIFO (Last-In, First-Out)."
    },
    {
        "question": "In PostgreSQL, which index type is specifically optimized for vector similarity search using cosine distance?",
        "options": [
            "B-Tree",
            "HNSW / IVFFlat (pgvector)",
            "GiST",
            "BRIN"
        ],
        "correct_index": 1,
        "explanation": "The pgvector extension uses HNSW and IVFFlat indexes to accelerate vector cosine and L2 distance searches."
    }
]

async def generate_trivia_question(guild_id: str = "global") -> Dict[str, Any]:
    """
    Generates a trivia question. Attempts to pull server lore facts from pgvector first,
    falling back to curated tech trivia.
    """
    if guild_id and guild_id != "global":
        try:
            lore_items = await search_server_lore(guild_id, query_text="rule fact history", top_k=3)
            if lore_items and len(lore_items) > 0:
                selected_lore = random.choice(lore_items)
                fact_text = selected_lore.get("content", "")
                if fact_text:
                    return {
                        "question": f"🧠 [Server Lore Trivia]: What fact is recorded about this server?",
                        "options": [
                            fact_text[:100],
                            "The server was founded in 1995.",
                            "All bot commands require superuser privileges.",
                            "The community strictly forbids discussing code."
                        ],
                        "correct_index": 0,
                        "explanation": f"This server lore fact was recorded under [{selected_lore.get('source_type', 'lore').upper()}]."
                    }
        except Exception as e:
            print(f"[Trivia Warning] Could not fetch server lore trivia: {e}")

    return random.choice(TECH_TRIVIA_BANK)
