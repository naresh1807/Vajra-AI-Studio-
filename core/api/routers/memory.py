"""Project memory / RAG semantic index."""

from __future__ import annotations

from fastapi import APIRouter

from core.api.deps import AUTH, db, events
from core.api.schemas import RagReindexRequest, RagSearchRequest
from core.rag import rag_manager

router = APIRouter()


@router.get("/api/rag/status", dependencies=AUTH)
async def rag_status(root: str) -> dict:
    return rag_manager.status(root)


@router.post("/api/rag/reindex", dependencies=AUTH)
async def rag_reindex(req: RagReindexRequest) -> dict:
    stats = await rag_manager.reindex(req.root)
    await db.record_indexed_files(req.root, stats.pop("paths", []))
    await events.record("report", note=f"rag reindex: {stats}")
    return stats


@router.post("/api/rag/search", dependencies=AUTH)
async def rag_search(req: RagSearchRequest) -> dict:
    hits = await rag_manager.retrieve(req.root, req.query, k=max(1, min(req.k, 20)))
    return {
        "hits": [
            {"ref": h.ref, "path": h.path, "start_line": h.start_line,
             "end_line": h.end_line, "score": round(h.score, 4), "text": h.text}
            for h in hits
        ]
    }
