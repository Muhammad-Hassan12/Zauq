import random
import logging
from typing import Dict, Any, List
from backend.memory.rag import search_server_lore

logger = logging.getLogger("zauq.trivia")

TECH_TRIVIA_BANK = [
    {
        "difficulty": "medium",
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
        "difficulty": "easy",
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
        "difficulty": "easy",
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
        "difficulty": "hard",
        "question": "In PostgreSQL, which index type is specifically optimized for vector similarity search using cosine distance?",
        "options": [
            "B-Tree",
            "HNSW / IVFFlat (pgvector)",
            "GiST",
            "BRIN"
        ],
        "correct_index": 1,
        "explanation": "The pgvector extension uses HNSW and IVFFlat indexes to accelerate vector cosine and L2 distance searches."
    },
    {
        "difficulty": "medium",
        "question": "What is the time complexity of searching for an element in a balanced Binary Search Tree (BST)?",
        "options": [
            "O(1)",
            "O(log n)",
            "O(n)",
            "O(n log n)"
        ],
        "correct_index": 1,
        "explanation": "In a balanced BST, each step cuts the remaining search space in half, resulting in O(log n) time complexity."
    },
    {
        "difficulty": "easy",
        "question": "Which Git command is used to combine changes from one branch into another?",
        "options": [
            "git merge",
            "git clone",
            "git push",
            "git init"
        ],
        "correct_index": 0,
        "explanation": "git merge combines the specified branch's commit history into the current active branch."
    },
    {
        "difficulty": "medium",
        "question": "What Docker flag is used to isolate a container with zero network access?",
        "options": [
            "--network host",
            "--network none",
            "--network bridge",
            "--no-internet"
        ],
        "correct_index": 1,
        "explanation": "--network none disables all networking interfaces inside the container, enforcing network sandbox isolation."
    },
    {
        "difficulty": "hard",
        "question": "In Python, which built-in function returns an iterator of tuples containing counts and values?",
        "options": [
            "zip()",
            "enumerate()",
            "map()",
            "filter()"
        ],
        "correct_index": 1,
        "explanation": "enumerate(iterable, start=0) yields (index, item) tuples as an iterator."
    }
]

async def generate_trivia_question(guild_id: str = "global", difficulty: str = "medium") -> Dict[str, Any]:
    if guild_id and guild_id != "global":
        try:
            lore_items = await search_server_lore(guild_id, query_text="rule fact history", top_k=3)
            if lore_items and len(lore_items) > 0:
                selected_lore = random.choice(lore_items)
                fact_text = selected_lore.get("content", "")
                if fact_text:
                    return {
                        "question": "🧠 [Server Lore Trivia]: What fact is recorded about this server?",
                        "options": [
                            fact_text[:100],
                            "The server was founded in 1995.",
                            "All bot commands require superuser privileges.",
                            "The community strictly forbids discussing code."
                        ],
                        "correct_index": 0,
                        "explanation": f"This server lore fact was recorded under [{selected_lore.get('source_type', 'lore').upper()}].",
                        "difficulty": difficulty
                    }
        except Exception as e:
            logger.warning(f"Could not fetch server lore trivia: {e}")

    filtered = [q for q in TECH_TRIVIA_BANK if q.get("difficulty") == difficulty]
    return random.choice(filtered) if filtered else random.choice(TECH_TRIVIA_BANK)
