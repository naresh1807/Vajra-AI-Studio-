"""Model router — the single interface agents call.

Selects primary -> fallback, retries *transient* failures with backoff, honours
429 Retry-After, trips a circuit breaker on a tier that keeps failing (so it
stops wasting time on a dead provider), and records latency / token / error
metrics. Agents stay ignorant of provider details.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from core.config import ModelConfig, get_model_config
from core.llm.nemotron_client import (
    ChatMessage,
    LLMClientError,
    LLMPermanentError,
    LLMRateLimited,
    LLMResponse,
    OpenAICompatClient,
    ToolSpec,
)

log = logging.getLogger("vajra.llm")

_BREAKER_THRESHOLD = 4      # consecutive failures before the tier is skipped
_BREAKER_COOLDOWN = 60.0    # seconds to skip it for

#: tier priority. "secondary" is only present when config.secondary is set, so
#: the loop skips over it for the common primary -> fallback setup.
_TIER_SEQUENCE = ("primary", "secondary", "fallback")


@dataclass
class _TierStats:
    requests: int = 0
    failures: int = 0
    rate_limited: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms_total: float = 0.0
    consecutive_failures: int = 0
    open_until: float = 0.0

    def is_open(self) -> bool:
        return time.monotonic() < self.open_until

    def ok(self, latency_ms: float, usage: dict) -> None:
        self.requests += 1
        self.latency_ms_total += latency_ms
        self.tokens_in += int(usage.get("prompt_tokens", 0) or 0)
        self.tokens_out += int(usage.get("completion_tokens", 0) or 0)
        self.consecutive_failures = 0
        self.open_until = 0.0

    def bad(self, *, rate_limited: bool = False) -> None:
        self.requests += 1
        self.failures += 1
        if rate_limited:
            self.rate_limited += 1
        self.consecutive_failures += 1
        if self.consecutive_failures >= _BREAKER_THRESHOLD:
            self.open_until = time.monotonic() + _BREAKER_COOLDOWN
            log.warning("circuit breaker: skipping this model tier for %ss", int(_BREAKER_COOLDOWN))

    def as_dict(self) -> dict:
        avg = round(self.latency_ms_total / self.requests, 1) if self.requests else 0.0
        return {
            "requests": self.requests, "failures": self.failures,
            "rate_limited": self.rate_limited, "avg_latency_ms": avg,
            "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
            "circuit": "open" if self.is_open() else "closed",
        }


@dataclass
class ModelRouter:
    config: ModelConfig = field(default_factory=get_model_config)
    #: "chat" (default) uses config as-is. "agent" swaps config.agent_model onto
    #: the primary tier - autonomous agents need capability over latency.
    role: str = "chat"

    def __post_init__(self) -> None:
        if self.role == "agent" and self.config.agent_model:
            # copy so we don't mutate the lru_cached shared config
            self.config = self.config.model_copy(deep=True)
            self.config.primary.model = self.config.agent_model
        self._clients = {
            "primary": OpenAICompatClient(self.config.primary),
            "fallback": OpenAICompatClient(self.config.fallback),
        }
        self._stats = {"primary": _TierStats(), "fallback": _TierStats()}
        if self.config.secondary is not None:
            self._clients["secondary"] = OpenAICompatClient(self.config.secondary)
            self._stats["secondary"] = _TierStats()

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
        last_exc: Exception | None = None
        for label in _TIER_SEQUENCE:
            client = self._clients.get(label)
            if client is None:
                continue  # tier not configured (the usual case for "secondary")
            stats = self._stats[label]
            if stats.is_open():
                log.info("model %s: circuit open, skipping", label)
                continue
            for attempt in range(1, self.transient_attempts + 1):
                started = time.monotonic()
                try:
                    resp = await client.chat(messages, tools, temperature, max_tokens)
                    stats.ok((time.monotonic() - started) * 1000, resp.usage)
                    return resp
                except asyncio.CancelledError:
                    raise
                except LLMPermanentError as exc:
                    stats.bad()
                    last_exc = exc
                    log.warning("model %s permanent error, moving on: %s", label, exc)
                    break  # retrying a 4xx is pointless - go to the next tier
                except LLMRateLimited as exc:
                    stats.bad(rate_limited=True)
                    last_exc = exc
                    wait = exc.retry_after or self.backoff_seconds * attempt
                    if attempt < self.transient_attempts:
                        await asyncio.sleep(min(wait, 30.0))
                except LLMClientError as exc:
                    stats.bad()
                    last_exc = exc
                    log.warning("model %s attempt %d failed: %s", label, attempt, exc)
                    if attempt < self.transient_attempts:
                        await asyncio.sleep(self.backoff_seconds * attempt)
            log.warning("model %s exhausted; trying next tier", label)
        raise LLMClientError(
            f"primary and fallback model providers both unavailable: {last_exc}"
        )

    def describe(self) -> dict[str, str]:
        d = {
            "primary": f"{self.config.primary.provider}:{self.config.primary.model}",
            "fallback": f"{self.config.fallback.provider}:{self.config.fallback.model}",
        }
        if self.config.secondary is not None:
            sec = self.config.secondary
            d["secondary"] = f"{sec.provider}:{sec.model}"
        return d

    def stats(self) -> dict:
        out: dict = {"models": self.describe()}
        for label in _TIER_SEQUENCE:
            if label in self._stats:
                out[label] = self._stats[label].as_dict()
        return out
