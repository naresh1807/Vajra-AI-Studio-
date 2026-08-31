"""OpenAI-compatible chat client.

Nemotron via NVIDIA NIM, and local runtimes (Ollama / vLLM / llama.cpp), all speak
the OpenAI chat-completions shape, so a single thin client covers every provider.
Tool schemas are kept provider-independent.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from core.config import ModelEndpoint

#: Nemotron/NIM models sometimes emit a tool call as a JSON object in the message
#: body instead of a proper ``tool_calls`` entry. Recover those so the agent loop
#: still makes progress. Matches ```json fences and bare top-level objects.
_TOOLCALL_FENCE = re.compile(r"```(?:json|tool_call)?\s*([\s\S]*?)```", re.IGNORECASE)


def _balanced_objects(text: str) -> list[str]:
    """Every top-level balanced ``{...}`` substring, in order (string-aware)."""
    spans: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "{":
            depth = 0
            in_str = esc = False
            for j in range(i, len(text)):
                c = text[j]
                if in_str:
                    esc = (c == "\\") and not esc
                    if c == '"' and not esc:
                        in_str = False
                elif c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        spans.append(text[i:j + 1])
                        i = j
                        break
        i += 1
    return spans


def _tool_calls_from_text(text: str) -> tuple[list[ToolCall], str]:
    """Pull ``{"name": ..., "arguments": {...}}`` tool calls out of a model reply
    that put them in the body. Returns (calls, text-with-those-blobs-removed)."""
    if not text or '"name"' not in text:
        return [], text
    candidates = (_TOOLCALL_FENCE.findall(text) or []) + _balanced_objects(text)
    calls: list[ToolCall] = []
    removed: list[str] = []
    seen: set[str] = set()
    for cand in candidates:
        try:
            obj = json.loads(cand.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("name"), str):
            continue
        if "arguments" not in obj and "parameters" not in obj:
            continue  # {"name": ...} with no args block is probably not a tool call
        args = obj.get("arguments", obj.get("parameters")) or {}
        if not isinstance(args, dict):
            continue
        key = obj["name"] + json.dumps(args, sort_keys=True, default=str)
        if key in seen:
            removed.append(cand)
            continue
        seen.add(key)
        calls.append(ToolCall(id=f"text-{len(calls)}", name=obj["name"], arguments=args))
        removed.append(cand)
    cleaned = text
    for blob in removed:
        cleaned = cleaned.replace(blob, "")
    cleaned = re.sub(r"```(?:json|tool_call)?\s*```", "", cleaned, flags=re.IGNORECASE).strip()
    return calls, cleaned


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
    """Transient failure - safe to retry / fall back (timeout, 5xx, connect)."""


class LLMPermanentError(LLMClientError):
    """A 4xx that retrying won't fix (bad request, auth, model not found)."""


class LLMRateLimited(LLMClientError):
    def __init__(self, message: str, retry_after: float = 0.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


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
        try:
            async with httpx.AsyncClient(timeout=self.endpoint.timeout_seconds) as client:
                resp = await client.post(url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as exc:
            raise LLMClientError(f"{self.endpoint.provider}: {type(exc).__name__}: {exc}") from exc

        if resp.status_code == 429:
            try:
                retry_after = float(resp.headers.get("retry-after", "0"))
            except ValueError:
                retry_after = 0.0
            raise LLMRateLimited(f"{self.endpoint.provider} rate limited", retry_after)
        if 400 <= resp.status_code < 500:
            raise LLMPermanentError(f"{self.endpoint.provider} {resp.status_code}: {resp.text[:500]}")
        if resp.status_code >= 500:
            raise LLMClientError(f"{self.endpoint.provider} {resp.status_code}: {resp.text[:300]}")
        data = resp.json()

        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        raw_calls = msg.get("tool_calls") or []
        tool_calls: list[ToolCall] = []
        for call in raw_calls:
            fn = call.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw": fn.get("arguments")}
            tool_calls.append(ToolCall(id=call.get("id", ""), name=fn.get("name", ""), arguments=args))

        text = msg.get("content") or ""
        if tools and not tool_calls:
            # some NIM models put the call in the body - recover it
            recovered, text = _tool_calls_from_text(text)
            tool_calls = recovered

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            model=data.get("model", self.endpoint.model),
            provider=self.endpoint.provider,
            usage=data.get("usage", {}) or {},
        )
