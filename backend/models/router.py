from typing import List, Dict, AsyncGenerator
from backend.config import settings
from backend.models.gemini_client import GeminiClient
from backend.models.openai_compatible_client import OpenAICompatibleClient
from backend.models.kaggle_client import KaggleClient

class ModelRouter:
    def __init__(self):
        self.gemini_client = GeminiClient()
        self.do_client = OpenAICompatibleClient(
            base_url="https://inference.do-ai.run/v1",
            api_key=settings.DO_MODEL_ACCESS_KEY,
            default_model="llama3.3-70b-instruct"
        )

    def _get_ollama_client(self) -> OpenAICompatibleClient:
        base_url = settings.OLLAMA_BASE_URL or "http://localhost:11434"
        if not base_url.endswith("/v1"):
            base_url = f"{base_url.rstrip('/')}/v1"
        return OpenAICompatibleClient(
            base_url=base_url,
            api_key="",
            default_model="qwen3.5:4b"
        )

    def _get_kaggle_client(self) -> KaggleClient:
        return KaggleClient(tunnel_url=settings.KAGGLE_TUNNEL_URL)

    async def generate(
        self,
        messages: List[Dict[str, str]],
        provider: str = "gemini",
        model_name: str = None,
        system_prompt: str = None,
        temperature: float = 0.7
    ) -> str:
        provider = provider.lower()
        if provider == "gemini":
            target_model = model_name or "gemini-2.5-flash"
            return await self.gemini_client.generate(messages, system_prompt, temperature)
        elif provider == "digitalocean":
            if not settings.DO_MODEL_ACCESS_KEY:
                raise ValueError("DigitalOcean Gradient Key (DO_MODEL_ACCESS_KEY) is not configured.")
            target_model = model_name if (model_name and model_name != "gemini-2.5-flash") else "llama3.3-70b-instruct"
            return await self.do_client.generate(messages, system_prompt, temperature, model_name=target_model)
        elif provider == "ollama":
            if not settings.OLLAMA_BASE_URL:
                raise ValueError("Tier 2 (Ollama) base URL is not configured.")
            ollama = self._get_ollama_client()
            target_model = model_name if (model_name and model_name != "gemini-2.5-flash") else "qwen3.5:4b"
            return await ollama.generate(messages, system_prompt, temperature, model_name=target_model)
        elif provider == "kaggle":
            kaggle = self._get_kaggle_client()
            return await kaggle.generate(messages, system_prompt, temperature)
        else:
            raise ValueError(f"Unknown model provider: '{provider}'")

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        provider: str = "gemini",
        model_name: str = None,
        system_prompt: str = None,
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        provider = provider.lower()
        if provider == "gemini":
            async for chunk in self.gemini_client.generate_stream(messages, system_prompt, temperature):
                yield chunk
        elif provider == "digitalocean":
            if not settings.DO_MODEL_ACCESS_KEY:
                raise ValueError("DigitalOcean Gradient Key (DO_MODEL_ACCESS_KEY) is not configured.")
            target_model = model_name if (model_name and model_name != "gemini-2.5-flash") else "llama3.3-70b-instruct"
            async for chunk in self.do_client.generate_stream(messages, system_prompt, temperature, model_name=target_model):
                yield chunk
        elif provider == "ollama":
            if not settings.OLLAMA_BASE_URL:
                raise ValueError("Tier 2 (Ollama) base URL is not configured.")
            ollama = self._get_ollama_client()
            target_model = model_name if (model_name and model_name != "gemini-2.5-flash") else "qwen3.5:4b"
            async for chunk in ollama.generate_stream(messages, system_prompt, temperature, model_name=target_model):
                yield chunk
        elif provider == "kaggle":
            kaggle = self._get_kaggle_client()
            async for chunk in kaggle.generate_stream(messages, system_prompt, temperature):
                yield chunk
        else:
            raise ValueError(f"Unknown model provider: '{provider}'")

model_router = ModelRouter()
