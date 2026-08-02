import httpx
from typing import List, Dict, Any, AsyncGenerator, Optional
from backend.config import settings

class GeminiClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.default_model = "gemini-2.5-flash"

    def _prepare_payload(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        image_parts: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        contents = []
        for idx, msg in enumerate(messages):
            role = "user" if msg.get("role") in ["user", "system"] else "model"
            parts = [{"text": msg.get("content", "")}]

            # Attach multimodal image parts to the final user message if present
            if idx == len(messages) - 1 and role == "user" and image_parts:
                for img in image_parts:
                    parts.append({
                        "inlineData": {
                            "mimeType": img.get("mime_type", "image/png"),
                            "data": img.get("bytes_b64", "")
                        }
                    })

            contents.append({
                "role": role,
                "parts": parts
            })
            
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": 4096
            }
        }
        if system_prompt:
            payload["systemInstruction"] = {
                "parts": [{"text": system_prompt}]
            }
        return payload

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        model_name: Optional[str] = None,
        image_parts: Optional[List[Dict[str, str]]] = None
    ) -> str:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment.")

        target_model = model_name or self.default_model
        if not target_model.startswith("models/"):
            model_path = target_model
        else:
            model_path = target_model.replace("models/", "")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:generateContent?key={self.api_key}"
        payload = self._prepare_payload(messages, system_prompt, temperature, image_parts)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"Gemini API Error ({response.status_code}) for model {model_path}: {response.text}")
            
            data = response.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                raise RuntimeError(f"Unexpected response structure from Gemini API: {data}")

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        model_name: Optional[str] = None,
        image_parts: Optional[List[Dict[str, str]]] = None
    ) -> AsyncGenerator[str, None]:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment.")

        target_model = model_name or self.default_model
        if not target_model.startswith("models/"):
            model_path = target_model
        else:
            model_path = target_model.replace("models/", "")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_path}:streamGenerateContent?key={self.api_key}&alt=sse"
        payload = self._prepare_payload(messages, system_prompt, temperature, image_parts)

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
