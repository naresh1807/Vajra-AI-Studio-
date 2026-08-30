"""Workspace tree/search + file read/write + editor-open."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from core.api.deps import AUTH, db, events
from core.api.schemas import (
    EditorOpenRequest,
    FileReadRequest,
    FileWriteRequest,
    SearchRequest,
    TreeRequest,
)
from core.workspace import (
    WorkspaceConflict,
    WorkspaceError,
    build_tree,
    read_file,
    search_workspace,
    write_file,
)

router = APIRouter()


def _tree(root: str, max_depth: int) -> dict:
    try:
        return build_tree(root, max_depth=max_depth).model_dump(exclude_none=True)
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/workspace/tree", dependencies=AUTH)
async def workspace_tree(root: str, max_depth: int = 6) -> dict:
    return _tree(root, max_depth)


@router.post("/api/workspace/tree", dependencies=AUTH)
async def workspace_tree_post(req: TreeRequest) -> dict:
    return _tree(req.root, req.max_depth)


@router.post("/api/workspace/search", dependencies=AUTH)
async def workspace_search(req: SearchRequest) -> dict:
    hits = await asyncio.to_thread(
        search_workspace,
        req.root, req.query,
        is_regex=req.is_regex, case_sensitive=req.case_sensitive,
        glob=req.glob or "*", max_hits=req.max_hits,
    )
    return {"hits": [h.model_dump() for h in hits], "truncated": len(hits) >= req.max_hits}


@router.post("/api/files/read", dependencies=AUTH)
async def files_read(req: FileReadRequest) -> dict:
    try:
        return read_file(req.root, req.path).model_dump()
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/files/write", dependencies=AUTH)
async def files_write(req: FileWriteRequest) -> dict:
    try:
        result = write_file(req.root, req.path, req.content, base_sha=req.base_sha)
    except WorkspaceConflict as exc:
        # 409: the file moved under the caller - hand back the current content
        raise HTTPException(409, detail={"conflict": True, "path": exc.path, "current": exc.current}) from exc
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    await events.record(
        "tool.result", tool="write_file", success=True, changed_files=[req.path], exit_code=0
    )
    await db.record_file_change(None, None, req.path)
    return result.model_dump()


@router.post("/api/files/diff", dependencies=AUTH)
async def files_diff(req: FileWriteRequest) -> dict:
    """Preview: diff `content` against the file on disk without writing."""
    import difflib

    try:
        current = read_file(req.root, req.path).content
    except WorkspaceError:
        current = ""
    diff = "".join(
        difflib.unified_diff(
            current.splitlines(keepends=True), req.content.splitlines(keepends=True),
            fromfile=f"a/{req.path}", tofile=f"b/{req.path}",
        )
    )
    return {"path": req.path, "diff": diff, "changed": diff != ""}


@router.post("/api/editor/open", dependencies=AUTH)
async def editor_open(req: EditorOpenRequest) -> dict:
    try:
        return read_file(req.root, req.path).model_dump()
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
