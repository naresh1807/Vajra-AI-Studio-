"""Language server: diagnostics / completion / hover / definition / support."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from core.api.deps import AUTH
from core.api.schemas import LspRequest
from core.lsp import lsp_manager
from core.lsp.config import declared_languages as lsp_declared
from core.lsp.config import supported as lsp_supported

router = APIRouter()


@router.get("/api/lsp/support", dependencies=AUTH)
async def lsp_support() -> dict:
    return {"languages": lsp_supported(), "declared": lsp_declared(), "servers": lsp_manager.status()}


@router.post("/api/lsp/diagnostics", dependencies=AUTH)
async def lsp_diagnostics(req: LspRequest) -> dict:
    client = await lsp_manager.sync(req.root, req.path, req.content, req.language)
    if not client:
        return {"supported": False, "diagnostics": []}
    for _ in range(8):
        await asyncio.sleep(0.35)
        if client.diagnostics(req.path):
            break
    return {"supported": True, "diagnostics": client.diagnostics(req.path)}


@router.post("/api/lsp/completion", dependencies=AUTH)
async def lsp_completion(req: LspRequest) -> dict:
    client = await lsp_manager.sync(req.root, req.path, req.content, req.language)
    if not client:
        return {"supported": False, "items": []}
    await asyncio.sleep(0.1)
    items = await client.completion(req.path, req.line, req.character)
    return {"supported": True, "items": items[:200]}


@router.post("/api/lsp/hover", dependencies=AUTH)
async def lsp_hover(req: LspRequest) -> dict:
    client = await lsp_manager.sync(req.root, req.path, req.content, req.language)
    if not client:
        return {"supported": False, "value": None}
    await asyncio.sleep(0.1)
    return {"supported": True, "value": await client.hover(req.path, req.line, req.character)}


@router.post("/api/lsp/definition", dependencies=AUTH)
async def lsp_definition(req: LspRequest) -> dict:
    client = await lsp_manager.sync(req.root, req.path, req.content, req.language)
    if not client:
        return {"supported": False, "locations": []}
    await asyncio.sleep(0.1)
    return {"supported": True, "locations": await client.definition(req.path, req.line, req.character)}
