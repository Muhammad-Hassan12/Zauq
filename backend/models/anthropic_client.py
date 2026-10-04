from backend.memory.usage import record_usage
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
from backend.config import settings
from backend.models.gemini_client import sanitize_response_output
from backend.models.capabilities import supports_thinking, supports_vision

logger = logging.getLogger("zauq.anthropic_client")


from backend.agent.types import AgentModelTurn, ToolCall, ToolResultMessage
from backend.models.tool_schemas import to_anthropic_tools, normalize_tool_call_name
from backend.tools.aliases import canonical_to_alias

class AnthropicClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        self.base_url = (base_url or getattr(settings, "ANTHROPIC_BASE_URL", "https://api.anthropic.com") or "https://api.anthropic.com").rstrip("/")
        self.api_key = api_key if api_key is not None else getattr(settings, "ANTHROPIC_API_KEY", "")
        self.default_model = default_model or getattr(settings, "ANTHROPIC_DEFAULT_MODEL", "claude-sonnet-4-5") or "claude-sonnet-4-5"

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError("Anthropic API key (ANTHROPIC_API_KEY) is not configured.")
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _format_messages_and_system(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        media_parts: Optional[List[Dict[str, str]]] = None,
        model_name: Optional[str] = None,
    ) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """Separates system prompt from messages and formats media/tool blocks natively for Anthropic."""
        system_parts: List[str] = []
        if system_prompt:
            system_parts.append(system_prompt.strip())

        formatted_messages: List[Dict[str, Any]] = []
        for raw_msg in messages:
            msg = raw_msg.to_dict() if isinstance(raw_msg, ToolResultMessage) else raw_msg
            role = msg.get("role", "user")
            content = msg.get("content", "")
            continuation = msg.get('_provider_continuation', {})
            if role in ('assistant', 'model') and continuation.get('provider') == 'anthropic':
                import copy
                formatted_messages.append({'role':'assistant','content':copy.deepcopy(continuation['content'])})
                continue

            if role == "system":
                if content:
                    system_parts.append(str(content).strip())
                continue

            if role == "tool":
                call_id = msg.get("tool_call_id", "")
                result_content = msg.get("content", "")
                is_err = bool(msg.get("is_error", False))
                formatted_messages.append({
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": call_id,
                            "content": str(result_content),
                            "is_error": is_err,
                        }
                    ]
                })
                continue

            if role in ["assistant", "model"] and msg.get("tool_calls"):
                blocks: List[Dict[str, Any]] = []
                if content:
                    blocks.append({"type": "text", "text": str(content)})
                for tc in msg.get("tool_calls", []):
                    tc_id = tc.get("id", "") if isinstance(tc, dict) else tc.id
                    tc_name = tc.get("name", "") if isinstance(tc, dict) else tc.name
                    alias_name = canonical_to_alias(tc_name) if "." in tc_name else tc_name
                    tc_args = tc.get("arguments", {}) if isinstance(tc, dict) else tc.arguments
                    blocks.append({
                        "type": "tool_use",
                        "id": tc_id,
                        "name": alias_name,
                        "input": tc_args,
                    })
                formatted_messages.append({
                    "role": "assistant",
                    "content": blocks
                })
                continue

            anthropic_role = "assistant" if role in ["assistant", "model", "bot"] else "user"
            formatted_messages.append({
                "role": anthropic_role,
                "content": str(content)
            })

        if media_parts and formatted_messages and supports_vision("anthropic", model_name):
            image_blocks = []
            for part in media_parts:
                p_type = part.get("type", "")
                mime = part.get("mime_type", "image/png")
                b64 = part.get("bytes_b64", "")
                if (p_type == "image" or "image" in mime) and b64:
                    image_blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime,
                            "data": b64,
                        }
                    })

            if image_blocks:
                last_msg = next((m for m in reversed(formatted_messages) if m['role'] == 'user' and not (isinstance(m['content'], list) and any(b.get('type') == 'tool_result' for b in m['content']))), None)
                if last_msg is None:
                    return ('\n\n'.join(system_parts) or None), formatted_messages
                existing_text = last_msg["content"]
                blocks: List[Dict[str, Any]] = list(image_blocks)
                if isinstance(existing_text, list):
                    blocks.extend(existing_text)
                elif existing_text:
                    blocks.append({"type": "text", "text": existing_text})
                last_msg["content"] = blocks

        merged = []
        for msg in formatted_messages:
            if merged and merged[-1]['role'] == msg['role']:
                for item in (merged[-1], msg):
                    if isinstance(item['content'], str):
                        item['content'] = [{'type':'text','text':item['content']}]
                merged[-1]['content'].extend(msg['content'])
            else:
                merged.append(msg)
        formatted_messages = merged
        combined_system = "\n\n".join(system_parts).strip() if system_parts else None
        return combined_system, formatted_messages

    async def generate(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        model_name: Optional[str] = None,
        media_parts: Optional[List[Dict[str, str]]] = None,
        thinking_enabled: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Generates complete text response from Anthropic Claude Messages API."""
        if not self.api_key:
            raise ValueError("Anthropic API key (ANTHROPIC_API_KEY) is not configured.")

        model = model_name or self.default_model
        url = f"{self.base_url}/v1/messages"
        system, formatted_msgs = self._format_messages_and_system(
            messages, system_prompt, media_parts, model_name=model
        )

        max_tokens = 8192 if thinking_enabled else 4096

        payload: Dict[str, Any] = {
            "model": model,
            "messages": formatted_msgs,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if system:
            payload["system"] = system

        if thinking_enabled and supports_thinking("anthropic", model):
            payload["thinking"] = {"type": "enabled", "budget_tokens": 2048}
            payload["temperature"] = 1.0
            payload["max_tokens"] = 16384
        else:
            payload["temperature"] = max(0.0, min(1.0, temperature))

        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            if response.status_code != 200:
                raise RuntimeError(
                    f"Anthropic API Error ({response.status_code}) for model '{model}': {response.text}"
                )

            data = response.json()
            record_usage('anthropic', payload.get("model", self.default_model), data)
            try:
                text_blocks = [
                    b["text"] for b in data.get("content", []) if b.get("type") == "text"
                ]
                raw_text = "\n".join(text_blocks)
                return sanitize_response_output(raw_text)
            except Exception as e:
                raise RuntimeError(f"Unexpected response format from Anthropic API: {data} ({e})")

    async def generate_stream(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        model_name: Optional[str] = None,
        media_parts: Optional[List[Dict[str, str]]] = None,
        thinking_enabled: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[str, None]:
        """Streams response tokens from Anthropic Claude Messages API using SSE."""
        if not self.api_key:
            raise ValueError("Anthropic API key (ANTHROPIC_API_KEY) is not configured.")

        model = model_name or self.default_model
        url = f"{self.base_url}/v1/messages"
        system, formatted_msgs = self._format_messages_and_system(
            messages, system_prompt, media_parts, model_name=model
        )

        max_tokens = 8192 if thinking_enabled else 4096

        payload: Dict[str, Any] = {
            "model": model,
            "messages": formatted_msgs,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if system:
            payload["system"] = system

        if thinking_enabled and supports_thinking("anthropic", model):
            payload["thinking"] = {"type": "enabled", "budget_tokens": 2048}
            payload["temperature"] = 1.0
            payload["max_tokens"] = 16384
        else:
            payload["temperature"] = max(0.0, min(1.0, temperature))

        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            async with client.stream("POST", url, json=payload, headers=self._headers()) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise RuntimeError(
                        f"Anthropic Streaming Error ({response.status_code}) for model '{model}': {err_body.decode(errors='replace')}"
                    )

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            event_data = json.loads(data_str)
                            event_type = event_data.get("type", "")

                            if event_type == "content_block_delta":
                                delta = event_data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    yield delta.get("text", "")
                            elif event_type == "error":
                                err = event_data.get("error", {})
                                raise RuntimeError(f"Anthropic Stream Error: {err.get('message', 'unknown')}")
                        except (json.JSONDecodeError, KeyError):
                            continue

    async def generate_agent_turn(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Any]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        model_name: Optional[str] = None,
        media_parts: Optional[List[Dict[str, str]]] = None,
        thinking_enabled: bool = False,
    ) -> AgentModelTurn:
        """Normalized model step in the agent loop for Anthropic Claude native tool use."""
        if not self.api_key:
            raise ValueError("Anthropic API key (ANTHROPIC_API_KEY) is not configured.")

        model = model_name or self.default_model
        url = f"{self.base_url}/v1/messages"
        system, formatted_msgs = self._format_messages_and_system(
            messages, system_prompt, media_parts, model_name=model
        )

        max_tokens = 8192 if thinking_enabled else 4096

        payload: Dict[str, Any] = {
            "model": model,
            "messages": formatted_msgs,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if system:
            payload["system"] = system

        if thinking_enabled and supports_thinking("anthropic", model):
            payload["thinking"] = {"type": "enabled", "budget_tokens": 2048}
            payload["temperature"] = 1.0
            payload["max_tokens"] = 16384
        else:
            payload["temperature"] = max(0.0, min(1.0, temperature))

        if tools:
            payload["tools"] = to_anthropic_tools(tools)

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            if response.status_code != 200:
                raise RuntimeError(
                    f"Anthropic Agent Turn Error ({response.status_code}) for model '{model}': {response.text}"
                )

            data = response.json()
            record_usage('anthropic', payload.get("model", self.default_model), data)
            try:
                content_blocks = data.get("content", [])
                text_blocks: List[str] = []
                tool_calls: List[ToolCall] = []

                for block in content_blocks:
                    b_type = block.get("type", "")
                    if b_type == "text":
                        text_blocks.append(block.get("text", ""))
                    elif b_type == "tool_use":
                        call_id = block.get("id", "")
                        raw_name = block.get("name", "")
                        canon_name = normalize_tool_call_name(raw_name)
                        args = block.get("input") or {}
                        tool_calls.append(ToolCall(id=call_id, name=canon_name, arguments=args))

                raw_text = "\n".join(text_blocks)
                clean_text = sanitize_response_output(raw_text) if raw_text else None

                return AgentModelTurn(
                    text=clean_text if clean_text else None,
                    tool_calls=tool_calls,
                    raw_metadata=data,
                    provider_continuation={'provider':'anthropic', 'content':content_blocks},
                )
            except Exception as e:
                raise RuntimeError(f"Unexpected response format from Anthropic API: {data} ({e})")
