import json
import logging
from typing import Dict, Any
from backend.models.router import model_router

logger = logging.getLogger("zauq.moderation")

MODERATION_PROMPT = """You are an automated content moderation classifier.
Analyze the following user message and classify it for harmful content (severe toxicity, harassment, explicit hate speech, dangerous spam, or direct threats).
Output strictly valid JSON with the format:
{
  "classification": "safe | borderline | toxic",
  "reason": "Brief explanation if not safe",
  "severity": "low | medium | high"
}
If the message is normal or casual banter, return {"classification": "safe", "reason": "", "severity": "low"}.
"""

class ContentFilter:
    async def check_message(
        self, message_text: str, sensitivity: str = "medium"
    ) -> Dict[str, Any]:
        if not message_text or len(message_text.strip()) < 3:
            return {"classification": "safe", "reason": "", "severity": "low"}

        try:
            raw_output = await model_router.generate(
                messages=[{"role": "user", "content": f"Message to analyze: \"{message_text[:1000]}\""}],
                provider="gemini",
                model_name="gemini-2.5-flash",
                system_prompt=MODERATION_PROMPT,
                temperature=0.0
            )

            clean_json = raw_output.strip()
            if clean_json.startswith("```"):
                clean_json = clean_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            data = json.loads(clean_json)
            classification = data.get("classification", "safe").lower()

            # Adjust based on sensitivity
            if sensitivity == "high" and classification == "borderline":
                data["classification"] = "toxic"
            elif sensitivity == "low" and classification == "borderline":
                data["classification"] = "safe"

            return data
        except Exception as e:
            logger.error(f"Moderation check failed: {e}")
            return {"classification": "safe", "reason": f"Error: {e}", "severity": "low"}

content_filter = ContentFilter()
