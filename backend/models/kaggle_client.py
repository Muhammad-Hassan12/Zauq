import httpx
import json
from typing import List, Dict, AsyncGenerator
from backend.config import settings

class KaggleClient:
    def __init__(self, tunnel_url: str = None):
        self.tunnel_url = (tunnel_url or settings.KAGGLE_TUNNEL_URL).rstrip('/')

    async def ping(self) -> bool:
        if not self.tunnel_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.tunnel_url}/health")
                return res.status_code == 200
        except Exception:
            return False

    async def generate(self, messages: List[Dict[str, str]], system_prompt: str = None, temperature: float = 0.7) -> str:
        if not self.tunnel_url:
            raise ValueError("KAGGLE_TUNNEL_URL is not set.")

        is_online = await self.ping()
        if not is_online:
            raise RuntimeError("Tier 3 (Kaggle T4 Tunnel) is currently offline or unreachable.")

        url = f"{self.tunnel_url}/v1/chat/completions"
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        payload = {
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": False
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                raise RuntimeError(f"Kaggle API Error ({res.status_code}): {res.text}")
            data = res.json()
            return data["choices"][0]["message"]["content"]

    async def generate_stream(self, messages: List[Dict[str, str]], system_prompt: str = None, temperature: float = 0.7) -> AsyncGenerator[str, None]:
        if not self.tunnel_url:
            raise ValueError("KAGGLE_TUNNEL_URL is not set.")

        is_online = await self.ping()
        if not is_online:
            raise RuntimeError("Tier 3 (Kaggle T4 Tunnel) is currently offline or unreachable.")

        url = f"{self.tunnel_url}/v1/chat/completions"
        formatted_messages = []
        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt})
        formatted_messages.extend(messages)

        payload = {
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload) as res:
                if res.status_code != 200:
                    err = await res.aread()
                    raise RuntimeError(f"Kaggle Streaming Error ({res.status_code}): {err.decode()}")

                async for line in res.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content = data["choices"][0].get("delta", {}).get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
