import httpx
import json
from typing import List, Dict, Any, AsyncGenerator

class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str = "", default_model: str = "llama3.3-70b-instruct"):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.default_model = default_model

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def generate(self, messages: List[Dict[str, str]], system_prompt: str = None, temperature: float = 0.7, model_name: str = None) -> str:
        url = f"{self.base_url}/chat/completions"
        model = model_name or self.default_model

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": False
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI-Compatible API Error ({response.status_code}) from {self.base_url}: {response.text}")

            data = response.json()
            try:
                return data["choices"][0]["message"]["content"]
            except (KeyError, IndexError):
                raise RuntimeError(f"Unexpected response format from {self.base_url}: {data}")

    async def generate_stream(self, messages: List[Dict[str, str]], system_prompt: str = None, temperature: float = 0.7, model_name: str = None) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/chat/completions"
        model = model_name or self.default_model

        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload, headers=self._headers()) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RuntimeError(f"OpenAI-Compatible Streaming Error ({response.status_code}) from {self.base_url}: {error_text.decode()}")

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
