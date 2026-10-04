from backend.memory.usage import record_usage
import httpx
import json
import logging
from typing import List, Dict, Any, AsyncGenerator, Optional
from backend.models.gemini_client import sanitize_response_output

from backend.agent.types import AgentModelTurn, ToolCall, ToolResultMessage
from backend.models.tool_schemas import to_openai_tools, normalize_tool_call_name
from backend.tools.aliases import canonical_to_alias

logger = logging.getLogger("zauq.openai_client")

class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str = "", default_model: str = "llama3.3-70b-instruct", provider_id: str = "openai_compatible"):
        self.provider_id = provider_id
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.default_model = default_model

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _format_messages(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        thinking_enabled: bool = False
    ) -> List[Dict[str, Any]]:
        effective_system_prompt = system_prompt or ""
        formatted: List[Dict[str, Any]] = []
        if effective_system_prompt:
            formatted.append({"role": "system", "content": effective_system_prompt})

        for raw_msg in messages:
            msg = raw_msg.to_dict() if isinstance(raw_msg, ToolResultMessage) else raw_msg
            role = msg.get("role", "user")
            continuation = msg.get('_provider_continuation', {})
            if role in ('assistant', 'model') and continuation.get('provider') == 'openai_compatible':
                import copy
                formatted.append(copy.deepcopy(continuation['content']))
                continue

            if role == "tool":
                call_id = msg.get("tool_call_id", "")
                name = msg.get("tool_name") or msg.get("name", "")
                alias = canonical_to_alias(name) if "." in name else name
                formatted.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": alias,
                    "content": str(msg.get("content", ""))
                })
                continue

            if role in ["assistant", "model"] and msg.get("tool_calls"):
                raw_calls = []
                for tc in msg.get("tool_calls", []):
                    tc_id = tc.get("id", "") if isinstance(tc, dict) else tc.id
                    tc_name = tc.get("name", "") if isinstance(tc, dict) else tc.name
                    alias_name = canonical_to_alias(tc_name) if "." in tc_name else tc_name
                    tc_args = tc.get("arguments", {}) if isinstance(tc, dict) else tc.arguments
                    args_str = json.dumps(tc_args) if isinstance(tc_args, dict) else str(tc_args)
                    raw_calls.append({
                        "id": tc_id,
                        "type": "function",
                        "function": {
                            "name": alias_name,
                            "arguments": args_str
                        }
                    })
                formatted.append({
                    "role": "assistant",
                    "content": msg.get("content") or None,
                    "tool_calls": raw_calls
                })
                continue

            formatted.append({
                "role": role,
                "content": str(msg.get("content", ""))
            })

        return formatted

    async def generate(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        model_name: Optional[str] = None,
        thinking_enabled: bool = False
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        model = model_name or self.default_model
        formatted_messages = self._format_messages(messages, system_prompt, thinking_enabled)

        max_output = 32768 if thinking_enabled else 16384

        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_output,
            "stream": False
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI-Compatible API Error ({response.status_code}) from {self.base_url} for model '{model}': {response.text}")

            data = response.json()
            record_usage(self.provider_id, payload.get("model", self.default_model), data)
            try:
                raw_text = data["choices"][0]["message"]["content"]
                return sanitize_response_output(raw_text)
            except (KeyError, IndexError):
                raise RuntimeError(f"Unexpected response format from {self.base_url}: {data}")

    async def generate_agent_turn(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Any]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        model_name: Optional[str] = None,
        thinking_enabled: bool = False,
    ) -> AgentModelTurn:
        """Normalized model step in the agent loop for OpenAI-compatible tools."""
        url = f"{self.base_url}/chat/completions"
        model = model_name or self.default_model
        formatted_messages = self._format_messages(messages, system_prompt, thinking_enabled)

        max_output = 32768 if thinking_enabled else 16384

        payload: Dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_output,
            "stream": False
        }

        if tools:
            payload["tools"] = to_openai_tools(tools)
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            if response.status_code != 200:
                raise RuntimeError(f"OpenAI-Compatible Agent Turn Error ({response.status_code}) from {self.base_url} for model '{model}': {response.text}")

            data = response.json()
            record_usage(self.provider_id, payload.get("model", self.default_model), data)
            try:
                choice = data["choices"][0]["message"]
                raw_content = choice.get("content")
                clean_text = sanitize_response_output(raw_content) if raw_content else None

                tool_calls: List[ToolCall] = []
                for tc in choice.get("tool_calls") or []:
                    call_id = tc.get("id", "")
                    func = tc.get("function", {})
                    raw_name = func.get("name", "")
                    canon_name = normalize_tool_call_name(raw_name)
                    raw_args = func.get("arguments", "{}")
                    if isinstance(raw_args, str):
                        try:
                            args = json.loads(raw_args)
                        except json.JSONDecodeError:
                            args = {"raw_args": raw_args}
                    else:
                        args = raw_args or {}

                    tool_calls.append(ToolCall(id=call_id, name=canon_name, arguments=args))

                return AgentModelTurn(
                    text=clean_text if clean_text else None,
                    tool_calls=tool_calls,
                    raw_metadata=data,
                    provider_continuation={'provider':'openai_compatible','content':choice},
                )
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Unexpected response format from {self.base_url}: {data} ({e})")

    async def generate_stream(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        model_name: Optional[str] = None,
        thinking_enabled: bool = False
    ) -> AsyncGenerator[str, None]:
        url = f"{self.base_url}/chat/completions"
        model = model_name or self.default_model

        formatted_messages = self._format_messages(messages, system_prompt, thinking_enabled)

        max_output = 32768 if thinking_enabled else 16384

        payload = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_output,
            "stream": True
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            async with client.stream("POST", url, json=payload, headers=self._headers()) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise RuntimeError(f"OpenAI-Compatible Streaming Error ({response.status_code}) from {self.base_url} for model '{model}': {error_text.decode()}")

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
