"""OpenAI-compatible chat client.

Nemotron via NVIDIA NIM, and local runtimes (Ollama / vLLM / llama.cpp), all speak
the OpenAI chat-completions shape, so a single thin client covers every provider.
Tool schemas are kept provider-independent.
"""

from __future__ import annotations

from typing import Any, Literal

import httpx
from pydantic import BaseModel

from core.config import ModelEndpoint


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    name: str | None = None


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]

    def to_openai(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class LLMResponse(BaseModel):
    text: str
    tool_calls: list[ToolCall] = []
    model: str
    provider: str
    usage: dict[str, int] = {}


class LLMClientError(RuntimeError):
    pass


class OpenAICompatClient:
    def __init__(self, endpoint: ModelEndpoint) -> None:
        self.endpoint = endpoint

    async def chat(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        if not self.endpoint.base_url:
            raise LLMClientError(f"No base_url configured for provider {self.endpoint.provider}")

        headers = {"Content-Type": "application/json"}
        if self.endpoint.api_key:
            headers["Authorization"] = f"Bearer {self.endpoint.api_key}"

        body: dict[str, Any] = {
            "model": self.endpoint.model,
            "messages": [m.model_dump(exclude_none=True) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = [t.to_openai() for t in tools]
            body["tool_choice"] = "auto"

        url = self.endpoint.base_url.rstrip("/") + "/chat/completions"
        async with httpx.AsyncClient(timeout=self.endpoint.timeout_seconds) as client:
            resp = await client.post(url, json=body, headers=headers)
            if resp.status_code >= 400:
                raise LLMClientError(f"{self.endpoint.provider} {resp.status_code}: {resp.text[:500]}")
            data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        raw_calls = msg.get("tool_calls") or []
        tool_calls: list[ToolCall] = []
        for call in raw_calls:
            fn = call.get("function", {})
            import json

            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments")}
            tool_calls.append(ToolCall(id=call.get("id", ""), name=fn.get("name", ""), arguments=args))

        return LLMResponse(
            text=msg.get("content") or "",
            tool_calls=tool_calls,
            model=data.get("model", self.endpoint.model),
            provider=self.endpoint.provider,
            usage=data.get("usage", {}) or {},
        )
