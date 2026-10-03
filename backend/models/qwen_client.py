"""Alibaba Cloud Model Studio / Qwen Direct API Client for Zauq AI.

Direct first-party connectivity to official Qwen OpenAI-compatible endpoints.
Maintains independent provider identity, telemetry, capability mapping, and credentials.
"""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
from backend.config import settings
from backend.models.gemini_client import sanitize_response_output
from backend.models.capabilities import supports_thinking

from backend.agent.types import AgentModelTurn, ToolCall, ToolResultMessage
from backend.models.tool_schemas import to_openai_tools, normalize_tool_call_name
from backend.tools.aliases import canonical_to_alias

logger = logging.getLogger("zauq.qwen_client")


class QwenClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        default_model: Optional[str] = None,
    ):
        raw_url = base_url if base_url is not None else getattr(settings, "QWEN_BASE_URL", "")
        self.base_url = raw_url.rstrip("/") if raw_url else ""
        self.api_key = api_key if api_key is not None else getattr(settings, "QWEN_API_KEY", "")
        self.default_model = default_model or getattr(settings, "QWEN_DEFAULT_MODEL", "qwen-turbo") or "qwen-turbo"

    def _headers(self) -> Dict[str, str]:
        if not self.api_key:
            raise ValueError("Alibaba Qwen API key (QWEN_API_KEY) is not configured.")
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        messages: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        model_name: Optional[str] = None,
        thinking_enabled: bool = False,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[str, Dict[str, Any]]:
        model = model_name or self.default_model
        formatted_messages: List[Dict[str, Any]] = []

        if system_prompt:
            formatted_messages.append({"role": "system", "content": system_prompt.strip()})

        for raw_msg in messages:
            msg = raw_msg.to_dict() if isinstance(raw_msg, ToolResultMessage) else raw_msg
            role = msg.get("role", "user")

            # 1. Tool execution result
            if role == "tool":
                call_id = msg.get("tool_call_id", "")
                name = msg.get("tool_name") or msg.get("name", "")
                alias = canonical_to_alias(name) if "." in name else name
                formatted_messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": alias,
                    "content": str(msg.get("content", ""))
                })
                continue

            # 2. Assistant turn with prior tool calls
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
                formatted_messages.append({
                    "role": "assistant",
                    "content": msg.get("content") or None,
                    "tool_calls": raw_calls
                })
                continue

            # 3. Standard text message
            formatted_messages.append({
                "role": role,
                "content": str(msg.get("content", ""))
            })

        max_tokens = 32768 if thinking_enabled else 8192

        payload: Dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        if thinking_enabled and supports_thinking("qwen", model):
            payload["enable_thinking"] = True

        if tools:
            payload["tools"] = to_openai_tools(tools)
            payload["tool_choice"] = "auto"

        return model, payload

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
        """Generates text response from Alibaba Qwen API."""
        if not self.api_key:
            raise ValueError("Alibaba Qwen API key (QWEN_API_KEY) is not configured.")
        if not self.base_url:
            raise ValueError("Alibaba Qwen Base URL (QWEN_BASE_URL) is not configured.")

        model, payload = self._build_payload(
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            model_name=model_name,
            thinking_enabled=thinking_enabled,
            stream=False,
            tools=tools,
        )

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            if response.status_code != 200:
                raise RuntimeError(
                    f"Qwen API Error ({response.status_code}) from {self.base_url} for model '{model}': {response.text}"
                )

            data = response.json()
            try:
                raw_text = data["choices"][0]["message"]["content"]
                return sanitize_response_output(raw_text)
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Unexpected response format from Qwen API: {data} ({e})")

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
        """Streams response tokens from Alibaba Qwen API."""
        if not self.api_key:
            raise ValueError("Alibaba Qwen API key (QWEN_API_KEY) is not configured.")
        if not self.base_url:
            raise ValueError("Alibaba Qwen Base URL (QWEN_BASE_URL) is not configured.")

        model, payload = self._build_payload(
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            model_name=model_name,
            thinking_enabled=thinking_enabled,
            stream=True,
            tools=tools,
        )

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            async with client.stream("POST", url, json=payload, headers=self._headers()) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise RuntimeError(
                        f"Qwen Streaming Error ({response.status_code}) from {self.base_url} for model '{model}': {err_body.decode(errors='replace')}"
                    )

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:].strip()
                        if not data_str or data_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                            delta = data["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
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
        """Normalized model step in the agent loop for Alibaba Qwen."""
        if not self.api_key:
            raise ValueError("Alibaba Qwen API key (QWEN_API_KEY) is not configured.")
        if not self.base_url:
            raise ValueError("Alibaba Qwen Base URL (QWEN_BASE_URL) is not configured.")

        model, payload = self._build_payload(
            messages=messages,
            system_prompt=system_prompt,
            temperature=temperature,
            model_name=model_name,
            thinking_enabled=thinking_enabled,
            stream=False,
            tools=tools,
        )

        url = f"{self.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0)) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            if response.status_code != 200:
                raise RuntimeError(
                    f"Qwen Agent Turn Error ({response.status_code}) from {self.base_url} for model '{model}': {response.text}"
                )

            data = response.json()
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
                    raw_metadata=data
                )
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Unexpected response format from Qwen API: {data} ({e})")

