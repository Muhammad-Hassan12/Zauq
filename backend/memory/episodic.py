import asyncio
import json
import logging
from typing import List, Dict, Any
from backend.memory.db import db_helper
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
      "confidence": 0.9
    }
  ]
}
If no notable facts are found, return {"facts": []}.
"""

async def extract_and_store_user_memories(
    user_id: str,
    messages: List[Dict[str, str]],
    provider: str = "gemini",
    model_name: str = "gemini-2.5-flash"
):
    if not messages:
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

        for item in facts:
            fact_str = item.get("fact")
            if fact_str:
                category = item.get("category", "general")
                confidence = item.get("confidence", 1.0)
                await db_helper.add_user_memory(
                    user_id=user_id,
                    fact_content=fact_str,
                    category=category,
                    confidence_score=confidence
                )
                logger.info(f"Extracted fact for user {user_id}: {fact_str}")

    except Exception as e:
        logger.warning(f"Extraction failed for user {user_id}: {e}")
