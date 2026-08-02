import httpx
import logging
from typing import List
from backend.config import settings

logger = logging.getLogger("zauq.embeddings")

class EmbeddingClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"

    async def get_embedding(self, text: str) -> List[float]:
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. Returning 768-dim zero vector.")
            return [0.0] * 768

        url = f"{self.base_url}?key={self.api_key}"
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {
                "parts": [{"text": text}]
            },
            "outputDimensionality": 768
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code != 200:
                    logger.error(f"Embedding API Error ({response.status_code}): {response.text}")
                    return [0.0] * 768

                data = response.json()
                return data["embedding"]["values"]
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            return [0.0] * 768

embedding_client = EmbeddingClient()
