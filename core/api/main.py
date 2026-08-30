"""Vajra Local API — the secure localhost surface for Vajra AI Studio, Vajra
Mobile and the VS Code extension.

Auth: every /api/* (and /api/v1/*) request must present the device token via
`Authorization: Bearer <token>` or `X-Vajra-Token`. On first run the Core
generates a strong random device secret in ``data/device.json``; phones pair
with a one-time PIN. The API binds to 127.0.0.1 by default.

This module is only app wiring — the endpoints live in ``core/api/routers/*``
and the shared state in ``core/api/deps.py``.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.api import deps
from core.api.routers import ALL as _ROUTERS
from core.dap import dap_manager
from core.lsp import lsp_manager
from core.runtime import process_manager
from core.security.pairing import identity

settings = deps.settings
log = deps.log
# re-exported so tests can do `main.chat_agent.router = stub`, `main.orchestrator...`
router = deps.model_router
orchestrator = deps.orchestrator
chat_agent = deps.chat_agent
events = deps.events
db = deps.db

_LOCAL_ORIGINS = [
    "http://127.0.0.1:1420", "http://localhost:1420",
    "http://127.0.0.1:3000", "http://localhost:3000",
    "vscode-webview://vscode-webview", "vscode-file://vscode-app",
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.persist_task = asyncio.create_task(deps.persist_events())
    stale = await db.mark_interrupted_goals()  # P30: a crashed run
    if stale:
        log.warning("%d unfinished task(s) from the last session - GET /api/agent/interrupted", len(stale))
    log.info("Vajra Core up. models=%s  device=%s", router.describe(), identity().device_id)
    try:
        yield
    finally:
        app.state.persist_task.cancel()
        await process_manager.stop_all()
        await lsp_manager.shutdown_all()
        await dap_manager.shutdown_all()


app = FastAPI(title="Vajra Core API", version="0.3.0", lifespan=lifespan)

# P4: CORS scoped to local IDE / webview origins - never "*" for an
# authenticated computer-control API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_LOCAL_ORIGINS,
    allow_origin_regex=r"^(vscode-webview|vscode-file)://.*$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "X-Vajra-Token", "Content-Type"],
)


@app.middleware("http")
async def _v1_alias_and_rate_limit(request, call_next):
    p = request.scope["path"]
    if p.startswith("/api/v1/"):
        request.scope["path"] = "/api/" + p[len("/api/v1/"):]
    if request.method in ("POST", "PUT", "DELETE"):
        ip = request.client.host if request.client else "?"
        now = time.monotonic()
        bucket = deps.rate_buckets.setdefault(ip, [])
        bucket[:] = [t for t in bucket if now - t < 10.0]
        if len(bucket) >= 60:
            return JSONResponse({"detail": "rate limit: slow down"}, status_code=429)
        bucket.append(now)
    return await call_next(request)


for _r in _ROUTERS:
    app.include_router(_r)


def run() -> None:
    import uvicorn

    ident = identity()
    host = settings.bind_host
    if host == "0.0.0.0":  # noqa: S104
        configured = (settings.vajra_pairing_token or "").strip()
        # An unset token is fine - the auto-generated device secret is the guard.
        # Only refuse when a token IS set and it's a weak/known one.
        if configured and not ident.all_tokens_are_secure(configured):
            raise SystemExit(
                "Refusing to LAN-bind with an insecure VAJRA_PAIRING_TOKEN. Unset it to use the "
                f"auto-generated device secret, or set a strong one.\nsecret: {ident.device_secret}"
            )
        log.warning("Vajra Core is LAN-bound (0.0.0.0). Only do this on a trusted network.")
        log.info("pair a phone with PIN: GET /api/pairing/pin  |  or device secret: %s", ident.device_secret)
    log.info("device %s  |  pair a phone: GET /api/pairing/pin", ident.device_id)
    uvicorn.run("core.api.main:app", host=host, port=settings.vajra_port, reload=False)


if __name__ == "__main__":
    run()
