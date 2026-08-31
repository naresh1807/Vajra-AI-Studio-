"""Model-router resilience (master-prompt P17): retry, fallback, 429, circuit
breaker, permanent-error short-circuit, cancellation, metrics."""

from __future__ import annotations

import asyncio

import pytest

from core.config import ModelEndpoint
from core.llm import LLMPermanentError, LLMRateLimited, LLMResponse
from core.llm.model_router import ModelRouter, _TierStats
from core.llm.nemotron_client import LLMClientError


def _resp(provider: str) -> LLMResponse:
    return LLMResponse(
        text=f"ok from {provider}", model="m", provider=provider,
        usage={"prompt_tokens": 10, "completion_tokens": 5},
    )


class _Client:
    """Scripted fake: each call pops the next behaviour off `script`."""

    def __init__(self, provider: str, script: list) -> None:
        self.provider = provider
        self.script = list(script)
        self.calls = 0

    async def chat(self, *_a, **_kw) -> LLMResponse:
        self.calls += 1
        beh = self.script.pop(0) if self.script else "ok"
        if beh == "ok":
            return _resp(self.provider)
        if isinstance(beh, Exception):
            raise beh
        raise LLMClientError(f"{self.provider}: {beh}")


@pytest.fixture
def router():
    r = ModelRouter()
    # get_model_config() is lru_cached - copy so per-test tweaks don't leak.
    r.config = r.config.model_copy(deep=True)
    r.config.retry["transient_attempts"] = 3
    r.config.retry["backoff_seconds"] = 0  # no real sleeping in tests
    return r


def _wire(router, primary_script, fallback_script):
    router._clients["primary"] = _Client("primary", primary_script)
    router._clients["fallback"] = _Client("fallback", fallback_script)


def _wire3(router, primary_script, secondary_script, fallback_script):
    router.config.secondary = ModelEndpoint(provider="secondary", model="m", base_url="http://s")
    router._clients["secondary"] = _Client("secondary", secondary_script)
    router._stats["secondary"] = _TierStats()
    router._clients["primary"] = _Client("primary", primary_script)
    router._clients["fallback"] = _Client("fallback", fallback_script)


async def test_retries_then_succeeds(router):
    _wire(router, ["boom", "boom", "ok"], [])
    r = await router.complete([])
    assert r.provider == "primary"
    assert router._clients["primary"].calls == 3
    assert router.stats()["primary"]["requests"] == 3


async def test_falls_back_when_primary_exhausted(router):
    _wire(router, ["boom", "boom", "boom"], ["ok"])
    r = await router.complete([])
    assert r.provider == "fallback"
    assert router.stats()["primary"]["failures"] == 3


async def test_permanent_error_skips_retries(router):
    _wire(router, [LLMPermanentError("bad request"), LLMPermanentError("x"), "ok"], ["ok"])
    r = await router.complete([])
    assert r.provider == "fallback"
    assert router._clients["primary"].calls == 1  # did NOT retry the 4xx


async def test_rate_limit_counted(router):
    _wire(router, [LLMRateLimited("slow down", 0), LLMRateLimited("x", 0), "ok"], [])
    r = await router.complete([])
    assert r.provider == "primary"
    assert router.stats()["primary"]["rate_limited"] == 2


async def test_circuit_breaker_opens_and_skips(router):
    _wire(router, ["boom"] * 6, ["ok"] * 6)
    await router.complete([])  # primary fails 3x -> consecutive_failures=3
    await router.complete([])  # +3 -> >= threshold(4) -> circuit opens
    assert router.stats()["primary"]["circuit"] == "open"
    before = router._clients["primary"].calls
    r = await router.complete([])  # primary skipped entirely
    assert r.provider == "fallback"
    assert router._clients["primary"].calls == before


async def test_both_down_raises(router):
    _wire(router, ["boom"] * 3, ["boom"] * 3)
    with pytest.raises(LLMClientError):
        await router.complete([])


async def test_no_secondary_tier_by_default(router):
    _wire(router, ["boom"] * 3, ["ok"])
    r = await router.complete([])
    assert r.provider == "fallback"
    assert "secondary" not in router.stats()
    assert "secondary" not in router.describe()


async def test_secondary_tried_between_primary_and_fallback(router):
    _wire3(router, ["boom", "boom", "boom"], ["ok"], ["ok"])
    r = await router.complete([])
    assert r.provider == "secondary"
    assert router._clients["fallback"].calls == 0  # never reached the local fallback
    assert router.stats()["secondary"]["requests"] == 1
    assert "secondary" in router.describe()


async def test_secondary_exhausted_falls_through_to_fallback(router):
    _wire3(router, ["boom"] * 3, ["boom"] * 3, ["ok"])
    r = await router.complete([])
    assert r.provider == "fallback"
    assert router.stats()["secondary"]["failures"] == 3


async def test_all_three_tiers_down_raises(router):
    _wire3(router, ["boom"] * 3, ["boom"] * 3, ["boom"] * 3)
    with pytest.raises(LLMClientError):
        await router.complete([])


def test_agent_role_swaps_primary_model():
    from core.config import get_model_config

    cfg = get_model_config().model_copy(deep=True)
    cfg.agent_model = "vendor/big-agent-model"
    chat = ModelRouter(config=cfg.model_copy(deep=True))
    agent = ModelRouter(config=cfg.model_copy(deep=True), role="agent")
    assert agent.describe()["primary"].endswith("big-agent-model")
    assert chat.describe()["primary"] != agent.describe()["primary"]
    # fallback + secondary tiers are untouched by the role swap
    assert agent.describe()["fallback"] == chat.describe()["fallback"]


def test_agent_role_is_noop_without_agent_model():
    from core.config import get_model_config

    cfg = get_model_config().model_copy(deep=True)
    cfg.agent_model = None
    chat = ModelRouter(config=cfg.model_copy(deep=True))
    agent = ModelRouter(config=cfg.model_copy(deep=True), role="agent")
    assert agent.describe()["primary"] == chat.describe()["primary"]


async def test_cancellation_propagates(router):
    async def _slow(*_a, **_kw):
        await asyncio.sleep(10)

    router._clients["primary"].chat = _slow  # type: ignore[assignment]
    task = asyncio.create_task(router.complete([]))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_success_records_tokens_and_latency(router):
    _wire(router, ["ok"], [])
    await router.complete([])
    s = router.stats()["primary"]
    assert s["tokens_in"] == 10 and s["tokens_out"] == 5 and s["requests"] == 1
