"""The local fallback model - an OpenAI-compatible endpoint (Ollama / vLLM /
llama.cpp) the router falls back to when the primary NIM provider is
unreachable. Configuration comes from ``config/models.yaml`` + env
(``VAJRA_LOCAL_MODEL`` / ``VAJRA_LOCAL_BASE_URL``); this module only exposes
helpers so callers never hard-code the provider.
"""

from __future__ import annotations

import contextlib

import httpx

from core.config import ModelEndpoint, get_model_config


def local_endpoint() -> ModelEndpoint:
    return get_model_config().fallback


async def local_available(timeout: float = 3.0) -> bool:
    """Best-effort reachability probe for the local endpoint's /models list."""
    ep = local_endpoint()
    if not ep.base_url:
        return False
    with contextlib.suppress(httpx.HTTPError, OSError):
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{ep.base_url.rstrip('/')}/models")
        return r.status_code < 500
    return False
