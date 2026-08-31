"""Health, ping, root, and the Vajra Mobile page. Login lives in auth.py."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from core.api.deps import AUTH, agent_router, model_router
from core.api.schemas import SimpleOk

router = APIRouter()


@router.get("/")
async def root() -> dict:
    return {
        "service": "vajra-core",
        "version": "0.3.0",
        "docs": "/docs",
        "health": "/api/health",
        "hint": "all /api/* routes need an X-Vajra-Token or Authorization: Bearer header",
    }


@router.get("/api/health")
@router.get("/health")  # kept for the desktop sidecar's readiness probe
async def health() -> dict:
    models = model_router.describe()
    models["agent"] = agent_router.describe()["primary"]
    return {"status": "ok", "service": "vajra-core", "version": "0.3.0", "models": models}


@router.get("/api/ping", dependencies=AUTH)
async def ping() -> SimpleOk:
    return SimpleOk(detail="authenticated")


@router.get("/mobile", response_class=HTMLResponse)
async def mobile() -> str:
    from core.api.mobile import MOBILE_HTML

    return MOBILE_HTML
