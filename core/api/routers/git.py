"""Git / source control + checkpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.api.deps import AUTH, events
from core.api.schemas import (
    GitCheckpointRequest,
    GitCommitRequest,
    GitPathsRequest,
    GitRequest,
    GitRestoreRequest,
    SimpleOk,
)
from core.runtime import git as gitsvc

router = APIRouter()


@router.get("/api/git/status", dependencies=AUTH)
async def git_status(root: str) -> dict:
    st = await gitsvc.status(root)
    return {
        "is_repo": st.is_repo, "branch": st.branch, "ahead": st.ahead, "behind": st.behind,
        "files": [vars(f) for f in (st.files or [])],
    }


@router.get("/api/git/diff", dependencies=AUTH)
async def git_diff(root: str, path: str | None = None, staged: bool = False) -> dict:
    try:
        return {"diff": await gitsvc.diff(root, path, staged)}
    except gitsvc.GitError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/git/stage", dependencies=AUTH)
async def git_stage(req: GitPathsRequest) -> SimpleOk:
    await gitsvc.stage(req.root, req.paths)
    return SimpleOk()


@router.post("/api/git/unstage", dependencies=AUTH)
async def git_unstage(req: GitPathsRequest) -> SimpleOk:
    await gitsvc.unstage(req.root, req.paths)
    return SimpleOk()


@router.post("/api/git/discard", dependencies=AUTH)
async def git_discard(req: GitRequest) -> SimpleOk:
    if not req.path:
        raise HTTPException(400, "path required")
    await gitsvc.discard(req.root, req.path)
    return SimpleOk(detail=f"discarded {req.path}")


@router.post("/api/git/commit", dependencies=AUTH)
async def git_commit(req: GitCommitRequest) -> dict:
    try:
        sha = await gitsvc.commit(req.root, req.message)
    except gitsvc.GitError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "commit": sha}


@router.get("/api/git/checkpoints", dependencies=AUTH)
async def git_checkpoints(root: str) -> list[dict]:
    return await gitsvc.checkpoints(root)


@router.post("/api/git/checkpoint", dependencies=AUTH)
async def git_make_checkpoint(req: GitCheckpointRequest) -> dict:
    try:
        return await gitsvc.checkpoint(req.root, req.label)
    except gitsvc.GitError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/git/restore", dependencies=AUTH)
@router.post("/api/git/rollback", dependencies=AUTH)  # alias (master-prompt P1/P11)
async def git_restore(req: GitRestoreRequest) -> SimpleOk:
    try:
        await gitsvc.restore(req.root, req.target)
    except gitsvc.GitError as exc:
        raise HTTPException(400, str(exc)) from exc
    await events.record("report", note=f"restored to {req.target}")
    return SimpleOk(detail=f"restored to {req.target}")
