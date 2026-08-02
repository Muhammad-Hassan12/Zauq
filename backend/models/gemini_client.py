import httpx
from typing import List, Dict, Any, AsyncGenerator
from backend.config import settings

class GeminiClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash"

    def _prepare_payload(self, messages: List[Dict[str, str]], system_prompt: str = None, temperature: float = 0.7) -> Dict[str, Any]:
        contents = []
        for msg in messages:
            role = "user" if msg["role"] in ["user", "system"] else "model"
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}]
            })
            
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 2048
            }
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }
        return payload

    async def generate(self, messages: List[Dict[str, str]], system_prompt: str = None, temperature: float = 0.7) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment.")

        url = f"{self.base_url}:generateContent?key={self.api_key}"
        payload = self._prepare_payload(messages, system_prompt, temperature)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"Gemini API Error ({response.status_code}): {response.text}")
            
            data = response.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                raise RuntimeError(f"Unexpected response structure from Gemini API: {data}")

    async def generate_stream(self, messages: List[Dict[str, str]], system_prompt: str = None, temperature: float = 0.7) -> AsyncGenerator[str, None]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment.")

        url = f"{self.base_url}:streamGenerateContent?key={self.api_key}&alt=sse"
        payload = self._prepare_payload(messages, system_prompt, temperature)

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RuntimeError(f"Gemini Streaming Error ({response.status_code}): {error_text.decode()}")

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        json_str = line[6:].strip()
                        if not json_str:
                            continue
                        import json
                        try:
                            data = json.loads(json_str)
                            text_chunk = data["candidates"][0]["content"]["parts"][0]["text"]
                            yield text_chunk
                        except (KeyError, IndexError, json.JSONDecodeError):
                            continue
