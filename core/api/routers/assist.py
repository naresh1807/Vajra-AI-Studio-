"""Assisted coding: /api/assist, /api/format, /api/assist/complete."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.api.deps import AUTH, assist_agent, completion_agent
from core.api.schemas import AssistRequest, AssistResponse, FormatRequest, InlineCompleteRequest
from core.runtime import format as fmtsvc
from core.workspace import WorkspaceError, read_file

router = APIRouter()


@router.post("/api/assist", dependencies=AUTH)
async def assist(req: AssistRequest) -> AssistResponse:
    """Explain / fix / refactor / optimize / tests / document / security / edit.
    Edit actions return a *proposed* rewrite + diff; the client applies it via
    /api/files/write only after the user accepts."""
    try:
        content = read_file(req.root, req.path).content
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    result = await assist_agent.run(
        action=req.action,  # type: ignore[arg-type]
        path=req.path,
        file_content=content,
        selection=req.selection,
        instruction=req.instruction,
        language=req.language,
    )
    return AssistResponse(
        kind=result.kind, text=result.text, new_content=result.new_content, diff=result.diff
    )


@router.post("/api/format", dependencies=AUTH)
async def format_doc(req: FormatRequest) -> dict:
    try:
        formatted = await fmtsvc.format_document(req.root, req.path, req.content, req.language)
    except fmtsvc.FormatUnavailable as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"formatted": formatted, "changed": formatted != req.content}


@router.post("/api/assist/complete", dependencies=AUTH)
async def assist_complete(req: InlineCompleteRequest) -> dict:
    text = await completion_agent.complete(
        prefix=req.prefix, suffix=req.suffix, language=req.language, path=req.path
    )
    return {"text": text}
