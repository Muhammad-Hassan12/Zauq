import logging
from typing import List, Dict, Any, AsyncGenerator, Optional
from backend.config import settings
from backend.models.gemini_client import GeminiClient
from backend.models.openai_compatible_client import OpenAICompatibleClient
from backend.models.kaggle_client import KaggleClient
from backend.parsers.audio_transcriber import audio_transcriber
from backend.integrations.web_search import web_search_engine

logger = logging.getLogger("zauq.router")

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

    async def _handle_audio_fallback(self, messages: List[Dict[str, Any]], media_parts: Optional[List[Dict[str, str]]]):
        """Transcribes audio attachments for text-only model providers."""
        if not media_parts or not messages:
            return

        audio_parts = [m for m in media_parts if m.get("type") == "audio" or "audio" in m.get("mime_type", "")]
        for audio in audio_parts:
            b64_data = audio.get("bytes_b64", "")
            mime = audio.get("mime_type", "audio/ogg")
            if b64_data:
                transcript = await audio_transcriber.transcribe(b64_data, mime)
                if transcript and not transcript.startswith("[Audio transcription"):
                    target_msg = messages[-1]
                    original_content = target_msg.get("content", "")
                    if original_content == "[Voice Note Audio Input]" or not original_content:
                        target_msg["content"] = transcript
                    else:
                        target_msg["content"] = f"{original_content}\n\n[Transcribed Spoken Voice Note]: {transcript}"

    async def _handle_vision_fallback(self, messages: List[Dict[str, Any]], media_parts: Optional[List[Dict[str, str]]]):
        """For non-vision providers (DigitalOcean, Ollama, Kaggle), uses Gemini Flash Vision to extract full visual analysis & OCR."""
        if not media_parts or not messages:
            return

        image_parts = [m for m in media_parts if m.get("type") == "image" or "image" in m.get("mime_type", "")]
        for img in image_parts:
            b64_data = img.get("bytes_b64", "")
            mime = img.get("mime_type", "image/png")
            fname = img.get("filename", "image.png")
            if b64_data:
                try:
                    vision_prompt = (
                        "Analyze this image thoroughly in detail. Describe and transcribe all diagrams, flowcharts, "
                        "architecture components, mathematical formulas, equations, text, labels, code, and conceptual relationships "
                        "shown in this image so a technical assistant can answer questions about it precisely."
                    )
                    vision_res = await self.gemini_client.generate(
                        messages=[{"role": "user", "content": vision_prompt}],
                        system_prompt="You are an expert technical vision and OCR analysis engine. Extract and explain all components accurately.",
                        media_parts=[{"type": "image", "mime_type": mime, "bytes_b64": b64_data, "filename": fname}],
                        temperature=0.1
                    )
                    if vision_res and not vision_res.startswith("[Gemini API Error"):
                        target_msg = messages[-1]
                        target_msg["content"] += f"\n\n[Attached Image Visual Analysis & Transcription for '{fname}']:\n{vision_res}"
                        logger.info(f"Successfully generated vision description for {fname} via Gemini Vision fallback.")
                except Exception as e:
                    logger.warning(f"Vision fallback failed for {fname}: {e}")

    async def _handle_search_context(self, messages: List[Dict[str, Any]], enable_search: bool = False, category: str = "all"):
        """Fetches live search and deep roamed page contents and injects them into text-only prompts."""
        if not enable_search or not messages:
            return

        last_query = messages[-1].get("content", "")
        if not last_query or len(last_query.strip()) < 3:
            return

        search_data = await web_search_engine.deep_search_and_roam(
            query=last_query,
            max_results=5,
            roam_top_n=2,
            category=category
        )

        if search_data.get("context_text"):
            search_block = (
                f"\n\n[Live Deep Web Research Context for '{last_query[:60]}']:\n"
                f"{search_data['context_text']}\n\n"
                "Use the authoritative research information above to provide a comprehensive, accurate, and up-to-date answer. "
                "Include relevant source references if appropriate."
            )
            messages[-1]["content"] += search_block

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        provider: str = "gemini",
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        media_parts: Optional[List[Dict[str, str]]] = None,
        image_parts: Optional[List[Dict[str, str]]] = None,
        enable_search: bool = False
    ) -> str:
        provider = provider.lower()
        combined_media = (media_parts or []) + (image_parts or [])

        if provider == "gemini":
            target_model = model_name or "gemini-2.5-flash"
            return await self.gemini_client.generate(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                enable_search=enable_search
            )
        elif provider == "digitalocean":
            if not settings.DO_MODEL_ACCESS_KEY:
                raise ValueError("DigitalOcean Gradient Key (DO_MODEL_ACCESS_KEY) is not configured.")
            await self._handle_audio_fallback(messages, combined_media)
            await self._handle_vision_fallback(messages, combined_media)
            await self._handle_search_context(messages, enable_search)
            target_model = model_name if (model_name and model_name != "gemini-2.5-flash") else "llama3.3-70b-instruct"
            return await self.do_client.generate(messages, system_prompt, temperature, model_name=target_model)
        elif provider == "ollama":
            if not settings.OLLAMA_BASE_URL:
                raise ValueError("Tier 2 (Ollama) base URL is not configured.")
            await self._handle_audio_fallback(messages, combined_media)
            await self._handle_vision_fallback(messages, combined_media)
            await self._handle_search_context(messages, enable_search)
            ollama = self._get_ollama_client()
            target_model = model_name if (model_name and model_name != "gemini-2.5-flash") else "qwen3.5:4b"
            return await ollama.generate(messages, system_prompt, temperature, model_name=target_model)
        elif provider == "kaggle":
            await self._handle_audio_fallback(messages, combined_media)
            await self._handle_vision_fallback(messages, combined_media)
            await self._handle_search_context(messages, enable_search)
            kaggle = self._get_kaggle_client()
            return await kaggle.generate(messages, system_prompt, temperature)
        else:
            raise ValueError(f"Unknown model provider: '{provider}'")

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        provider: str = "gemini",
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        media_parts: Optional[List[Dict[str, str]]] = None,
        image_parts: Optional[List[Dict[str, str]]] = None,
        enable_search: bool = False
    ) -> AsyncGenerator[str, None]:
        provider = provider.lower()
        combined_media = (media_parts or []) + (image_parts or [])

        if provider == "gemini":
            target_model = model_name or "gemini-2.5-flash"
            async for chunk in self.gemini_client.generate_stream(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                enable_search=enable_search
            ):
                yield chunk
        elif provider == "digitalocean":
            if not settings.DO_MODEL_ACCESS_KEY:
                raise ValueError("DigitalOcean Gradient Key (DO_MODEL_ACCESS_KEY) is not configured.")
            await self._handle_audio_fallback(messages, combined_media)
            await self._handle_vision_fallback(messages, combined_media)
            await self._handle_search_context(messages, enable_search)
            target_model = model_name if (model_name and model_name != "gemini-2.5-flash") else "llama3.3-70b-instruct"
            async for chunk in self.do_client.generate_stream(messages, system_prompt, temperature, model_name=target_model):
                yield chunk
        elif provider == "ollama":
            if not settings.OLLAMA_BASE_URL:
                raise ValueError("Tier 2 (Ollama) base URL is not configured.")
            await self._handle_audio_fallback(messages, combined_media)
            await self._handle_vision_fallback(messages, combined_media)
            await self._handle_search_context(messages, enable_search)
            ollama = self._get_ollama_client()
            target_model = model_name if (model_name and model_name != "gemini-2.5-flash") else "qwen3.5:4b"
            async for chunk in ollama.generate_stream(messages, system_prompt, temperature, model_name=target_model):
                yield chunk
        elif provider == "kaggle":
            await self._handle_audio_fallback(messages, combined_media)
            await self._handle_vision_fallback(messages, combined_media)
            await self._handle_search_context(messages, enable_search)
            kaggle = self._get_kaggle_client()
            async for chunk in kaggle.generate_stream(messages, system_prompt, temperature):
                yield chunk
        else:
            raise ValueError(f"Unknown model provider: '{provider}'")

model_router = ModelRouter()
