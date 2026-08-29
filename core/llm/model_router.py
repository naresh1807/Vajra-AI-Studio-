"""Model router - the single interface agents call. Selects primary/fallback,
retries transient errors, and keeps agents ignorant of provider details.
"""

from __future__ import annotations

import asyncio
import logging

from core.config import ModelConfig, get_model_config
from core.llm.nemotron_client import (
    ChatMessage,
    LLMClientError,
    LLMResponse,
    OpenAICompatClient,
    ToolSpec,
)

log = logging.getLogger("vajra.llm")


class ModelRouter:
    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or get_model_config()
        self._primary = OpenAICompatClient(self.config.primary)
        self._fallback = OpenAICompatClient(self.config.fallback)

    @property
    def transient_attempts(self) -> int:
        return int(self.config.retry.get("transient_attempts", 3))

    @property
    def backoff_seconds(self) -> float:
        return float(self.config.retry.get("backoff_seconds", 2))

    async def complete(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        for client, label in ((self._primary, "primary"), (self._fallback, "fallback")):
            for attempt in range(1, self.transient_attempts + 1):
                try:
                    return await client.chat(messages, tools, temperature, max_tokens)
                except LLMClientError as exc:
                    log.warning("model %s attempt %d failed: %s", label, attempt, exc)
                    if attempt < self.transient_attempts:
                        await asyncio.sleep(self.backoff_seconds * attempt)
            log.warning("model %s exhausted; trying next tier", label)
        raise LLMClientError("primary and fallback model providers both unavailable")

    def describe(self) -> dict[str, str]:
        return {
            "primary": f"{self.config.primary.provider}:{self.config.primary.model}",
            "fallback": f"{self.config.fallback.provider}:{self.config.fallback.model}",
        }
