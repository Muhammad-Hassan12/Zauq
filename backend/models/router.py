import logging
from typing import List, Dict, Any, AsyncGenerator, Optional
from backend.config import settings
from backend.models.gemini_client import GeminiClient
from backend.models.openai_compatible_client import OpenAICompatibleClient
from backend.models.kaggle_client import KaggleClient
from backend.models.anthropic_client import AnthropicClient
from backend.models.qwen_client import QwenClient
from backend.models.deepseek_client import DeepSeekClient
from backend.models.catalog import normalize_provider_id, get_provider
from backend.models.capabilities import supports_audio, supports_vision, supports_native_tools
from backend.agent.types import AgentModelTurn
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
        self.anthropic_client = AnthropicClient()
        self.qwen_client = QwenClient()
        self.deepseek_client = DeepSeekClient()

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
        """For non-vision providers, uses Gemini Flash Vision to extract full visual analysis & OCR."""
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

        # Phase 9: Search Deduplication Guard — skip if web evidence was already injected upstream
        evidence_markers = (
            "[Live Deep Web Research Context",
            "[Autonomous Deep Web Research Context",
            "[Attached Live Webpage Content",
            "[Full-Page Web Research Context",
            "[Live Web Search Snippets",
        )
        if any(marker in last_query for marker in evidence_markers):
            logger.debug("Web evidence already present in prompt. Skipping duplicate search.")
            return

        from backend.search.service import search_service
        search_data = await search_service.search_and_fetch(
            query=last_query,
            max_results=5,
            fetch_top_n=2,
            category=category,
        )

        if search_data.get("context_text"):
            search_block = (
                f"\n\n[Live Deep Web Research Context for '{last_query[:60]}']:\n"
                f"{search_data['context_text']}\n\n"
                "Use the authoritative research information above to provide a comprehensive, accurate, and up-to-date answer. "
                "Include relevant source references if appropriate."
            )
            messages[-1]["content"] += search_block

    async def _preprocess_pipeline(
        self,
        messages: List[Dict[str, Any]],
        combined_media: List[Dict[str, str]],
        provider: str,
        target_model: str,
        enable_search: bool,
    ):
        """Unified pre-processing helper: audio transcription, vision OCR fallback, search context."""
        # 1. Audio fallback if provider/model cannot natively ingest audio
        if not supports_audio(provider, target_model):
            await self._handle_audio_fallback(messages, combined_media)

        # 2. Vision fallback if provider/model cannot natively accept images
        if not supports_vision(provider, target_model):
            await self._handle_vision_fallback(messages, combined_media)

        # 3. Search context injection if requested
        await self._handle_search_context(messages, enable_search)

    def _resolve_target_model(self, provider: str, model_name: Optional[str]) -> str:
        """Resolves target model, respecting provider defaults."""
        if model_name and model_name != "gemini-2.5-flash":
            return model_name
        spec = get_provider(provider)
        return spec.default_model if spec else (model_name or "gemini-2.5-flash")

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        provider: str = "gemini",
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        media_parts: Optional[List[Dict[str, str]]] = None,
        image_parts: Optional[List[Dict[str, str]]] = None,
        enable_search: bool = False,
        thinking_enabled: bool = False
    ) -> str:
        provider = normalize_provider_id(provider)
        combined_media = (media_parts or []) + (image_parts or [])
        target_model = self._resolve_target_model(provider, model_name)

        if provider == "gemini":
            target_model = model_name or "gemini-2.5-flash"
            return await self.gemini_client.generate(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                enable_search=enable_search,
                thinking_enabled=thinking_enabled
            )

        # Run unified preprocessing pipeline for non-Gemini providers
        await self._preprocess_pipeline(messages, combined_media, provider, target_model, enable_search)

        if provider == "digitalocean":
            if not settings.DO_MODEL_ACCESS_KEY:
                raise ValueError("DigitalOcean Gradient Key (DO_MODEL_ACCESS_KEY) is not configured.")
            return await self.do_client.generate(messages, system_prompt, temperature, model_name=target_model, thinking_enabled=thinking_enabled)

        elif provider == "anthropic":
            return await self.anthropic_client.generate(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                thinking_enabled=thinking_enabled,
            )

        elif provider == "qwen":
            return await self.qwen_client.generate(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                thinking_enabled=thinking_enabled,
            )

        elif provider == "deepseek":
            return await self.deepseek_client.generate(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                thinking_enabled=thinking_enabled,
            )

        elif provider == "ollama":
            if not settings.OLLAMA_BASE_URL:
                raise ValueError("Tier 2 (Ollama) base URL is not configured.")
            ollama = self._get_ollama_client()
            return await ollama.generate(messages, system_prompt, temperature, model_name=target_model, thinking_enabled=thinking_enabled)

        elif provider == "kaggle":
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
        enable_search: bool = False,
        thinking_enabled: bool = False
    ) -> AsyncGenerator[str, None]:
        provider = normalize_provider_id(provider)
        combined_media = (media_parts or []) + (image_parts or [])
        target_model = self._resolve_target_model(provider, model_name)

        if provider == "gemini":
            target_model = model_name or "gemini-2.5-flash"
            async for chunk in self.gemini_client.generate_stream(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                enable_search=enable_search,
                thinking_enabled=thinking_enabled
            ):
                yield chunk
            return

        # Run unified preprocessing pipeline for non-Gemini providers
        await self._preprocess_pipeline(messages, combined_media, provider, target_model, enable_search)

        if provider == "digitalocean":
            if not settings.DO_MODEL_ACCESS_KEY:
                raise ValueError("DigitalOcean Gradient Key (DO_MODEL_ACCESS_KEY) is not configured.")
            async for chunk in self.do_client.generate_stream(messages, system_prompt, temperature, model_name=target_model, thinking_enabled=thinking_enabled):
                yield chunk

        elif provider == "anthropic":
            async for chunk in self.anthropic_client.generate_stream(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                thinking_enabled=thinking_enabled,
            ):
                yield chunk

        elif provider == "qwen":
            async for chunk in self.qwen_client.generate_stream(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                thinking_enabled=thinking_enabled,
            ):
                yield chunk

        elif provider == "deepseek":
            async for chunk in self.deepseek_client.generate_stream(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                thinking_enabled=thinking_enabled,
            ):
                yield chunk

        elif provider == "ollama":
            if not settings.OLLAMA_BASE_URL:
                raise ValueError("Tier 2 (Ollama) base URL is not configured.")
            ollama = self._get_ollama_client()
            async for chunk in ollama.generate_stream(messages, system_prompt, temperature, model_name=target_model, thinking_enabled=thinking_enabled):
                yield chunk

        elif provider == "kaggle":
            kaggle = self._get_kaggle_client()
            async for chunk in kaggle.generate_stream(messages, system_prompt, temperature):
                yield chunk

        else:
            raise ValueError(f"Unknown model provider: '{provider}'")

    async def generate_agent_turn(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Any]] = None,
        provider: str = "gemini",
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        media_parts: Optional[List[Dict[str, str]]] = None,
        image_parts: Optional[List[Dict[str, str]]] = None,
        thinking_enabled: bool = False,
    ) -> AgentModelTurn:
        """Dispatches an agent turn with native tool-calling capabilities."""
        provider = normalize_provider_id(provider)
        combined_media = (media_parts or []) + (image_parts or [])
        target_model = self._resolve_target_model(provider, model_name)

        # Enforce capability check: unsupported providers cannot accidentally receive tool payloads
        if tools and not supports_native_tools(provider, target_model):
            raise ValueError(
                f"Provider '{provider}' with model '{target_model}' does not support native tool calling."
            )

        if provider == "gemini":
            target_model = model_name or "gemini-2.5-flash"
            return await self.gemini_client.generate_agent_turn(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                image_parts=image_parts,
                thinking_enabled=thinking_enabled,
            )

        # Run unified preprocessing pipeline for non-Gemini providers
        await self._preprocess_pipeline(messages, combined_media, provider, target_model, enable_search=False)

        if provider == "anthropic":
            return await self.anthropic_client.generate_agent_turn(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                thinking_enabled=thinking_enabled,
            )
        elif provider == "qwen":
            return await self.qwen_client.generate_agent_turn(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                thinking_enabled=thinking_enabled,
            )
        elif provider == "deepseek":
            return await self.deepseek_client.generate_agent_turn(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                media_parts=combined_media,
                thinking_enabled=thinking_enabled,
            )
        elif provider == "digitalocean":
            if not settings.DO_MODEL_ACCESS_KEY:
                raise ValueError("DigitalOcean Gradient Key (DO_MODEL_ACCESS_KEY) is not configured.")
            return await self.do_client.generate_agent_turn(
                messages=messages,
                tools=tools,
                system_prompt=system_prompt,
                temperature=temperature,
                model_name=target_model,
                thinking_enabled=thinking_enabled,
            )
        else:
            raise ValueError(f"Provider '{provider}' does not support agent turn generation.")


model_router = ModelRouter()

