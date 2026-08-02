import base64
import httpx
from typing import Optional
from backend.config import settings

class GeminiImageClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.GEMINI_API_KEY

    async def generate_image(self, prompt: str, model_name: str = "gemini-3.1-flash-image") -> bytes:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")

        # If model is imagen endpoint
        if "imagen" in model_name.lower():
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateImages?key={self.api_key}"
            payload = {
                "prompt": prompt,
                "numberOfImages": 1,
                "outputMimeType": "image/png",
                "aspectRatio": "1:1"
            }
            async with httpx.AsyncClient(timeout=45.0) as client:
                res = await client.post(url, json=payload)
                if res.status_code != 200:
                    raise RuntimeError(f"Imagen API Error ({res.status_code}): {res.text}")
                data = res.json()
                try:
                    b64_data = data["generatedImages"][0]["image"]["imageBytes"]
                    return base64.b64decode(b64_data)
                except (KeyError, IndexError) as e:
                    raise RuntimeError(f"Unexpected response structure from Imagen API: {data}")

        # Native Gemini multimodal image generation (gemini-3.1-flash-image / Nano Banana)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": f"Generate an image of: {prompt}"}]
                }
            ],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"]
            }
        }

        async with httpx.AsyncClient(timeout=45.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                # Fallback to imagen-3.0-generate-002 if gemini-3.1-flash-image returns 404 or unsupported modality
                fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-002:generateImages?key={self.api_key}"
                fallback_payload = {
                    "prompt": prompt,
                    "numberOfImages": 1,
                    "outputMimeType": "image/png",
                    "aspectRatio": "1:1"
                }
                fallback_res = await client.post(fallback_url, json=fallback_payload)
                if fallback_res.status_code == 200:
                    data = fallback_res.json()
                    try:
                        b64_data = data["generatedImages"][0]["image"]["imageBytes"]
                        return base64.b64decode(b64_data)
                    except (KeyError, IndexError):
                        pass
                raise RuntimeError(f"Gemini Image Gen Error ({res.status_code}): {res.text}")

            data = res.json()
            try:
                candidates = data.get("candidates", [])
                if not candidates:
                    raise RuntimeError(f"No image candidate generated: {data}")

                parts = candidates[0].get("content", {}).get("parts", [])
                for part in parts:
                    if "inlineData" in part:
                        b64_data = part["inlineData"]["data"]
                        return base64.b64decode(b64_data)

                # Fallback if image bytes not directly in inlineData
                raise RuntimeError(f"No inline image data found in response: {data}")
            except Exception as e:
                raise RuntimeError(f"Failed to parse Gemini image output: {str(e)}")

gemini_image_client = GeminiImageClient()
