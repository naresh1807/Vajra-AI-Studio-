"""Model router status / metrics (master-prompt P1 /api/models, P17)."""

from __future__ import annotations

from fastapi import APIRouter

from core.api.deps import AUTH, model_router

router = APIRouter()


@router.get("/api/models", dependencies=AUTH)
async def models() -> dict:
    return model_router.stats()
