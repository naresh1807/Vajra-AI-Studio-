"""Projects + the filesystem directory picker."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException

from core.api.deps import AUTH, db, events, log
from core.api.schemas import OpenProjectRequest, ProjectInfo
from core.rag import rag_manager
from core.workspace import discover_workspace

router = APIRouter()


async def _safe_reindex(root: str) -> None:
    try:
        stats = await rag_manager.reindex(root)
        await db.record_indexed_files(root, stats.pop("paths", []))
        await events.record("report", note=f"rag index ready: {stats}")
    except Exception as exc:  # noqa: BLE001
        log.warning("rag reindex failed for %s: %s", root, exc)


@router.post("/api/projects", dependencies=AUTH)
async def open_project(req: OpenProjectRequest) -> ProjectInfo:
    target = Path(req.root_path).expanduser()
    if not target.exists():
        if not req.create:
            raise HTTPException(400, f"folder does not exist: {target}")
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(400, f"cannot create folder: {exc}") from exc
    if not target.is_dir():
        raise HTTPException(400, f"not a directory: {target}")
    profile = discover_workspace(str(target))
    name = req.name or Path(profile.root).name or "project"
    pid = await db.upsert_project(name, profile.root, profile.model_dump())
    asyncio.create_task(_safe_reindex(profile.root))
    return ProjectInfo(id=pid, name=name, root_path=profile.root, profile=profile.model_dump())


@router.get("/api/projects", dependencies=AUTH)
async def list_projects() -> list[dict]:
    return await db.list_projects()


@router.get("/api/projects/{project_id}/context", dependencies=AUTH)
async def project_context(project_id: str) -> dict:
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "unknown project")
    return {"project": project, "profile": json.loads(project.get("profile_json") or "{}")}


@router.get("/api/fs/list", dependencies=AUTH)
async def fs_list(path: str = "") -> dict:
    """List sub-directories of `path` for a folder picker. Read-only, dirs only."""
    if not path:
        if os.name == "nt":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
            return {"path": "", "parent": None, "entries": [{"name": d, "path": d} for d in drives]}
        path = "/"

    base = Path(path).expanduser()
    if not base.is_dir():
        raise HTTPException(400, f"not a directory: {base}")
    base = base.resolve()
    entries = []
    try:
        for e in sorted(os.scandir(base), key=lambda x: x.name.lower()):
            if e.name.startswith(".") or e.name in {"$RECYCLE.BIN", "System Volume Information"}:
                continue
            with contextlib.suppress(OSError):
                if e.is_dir(follow_symlinks=False):
                    entries.append({"name": e.name, "path": str(Path(e.path).resolve())})
    except PermissionError as exc:
        raise HTTPException(403, f"permission denied: {base}") from exc
    parent = None if base.parent == base else str(base.parent)
    return {"path": str(base), "parent": parent, "entries": entries}


@router.post("/api/fs/mkdir", dependencies=AUTH)
async def fs_mkdir(req: OpenProjectRequest) -> dict:
    target = Path(req.root_path).expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(400, f"cannot create: {exc}") from exc
    return {"path": str(target.resolve())}
