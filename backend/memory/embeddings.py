import httpx
from typing import List
from backend.config import settings

class EmbeddingClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent"

    async def get_embedding(self, text: str) -> List[float]:
        if not self.api_key:
            # Fallback zero vector if key not set
            return [0.0] * 768

        url = f"{self.base_url}?key={self.api_key}"
        payload = {
            "model": "models/gemini-embedding-001",
            "content": {
                "parts": [{"text": text}]
            }
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                print(f"[Embedding Error] ({response.status_code}): {response.text}")
                return [0.0] * 768

            data = response.json()
            try:
                return data["embedding"]["values"]
            except (KeyError, IndexError):
                print(f"[Embedding Error] Invalid structure: {data}")
                return [0.0] * 768

embedding_client = EmbeddingClient()
