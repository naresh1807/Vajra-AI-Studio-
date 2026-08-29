"""Human-driven terminal (runs through the platform shell) + dev-server processes."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from core.api.deps import AUTH, db, events
from core.api.schemas import (
    ProcStartRequest,
    ProcStopRequest,
    SimpleOk,
    TerminalRunRequest,
    TerminalRunResult,
)
from core.runtime import process_manager
from core.runtime import terminal as termsvc

router = APIRouter()


@router.post("/api/terminal/run", dependencies=AUTH)
async def terminal_run(req: TerminalRunRequest) -> TerminalRunResult:
    res = await termsvc.run_terminal(req.root, req.command, req.timeout_seconds)
    await db.record_event(
        {"kind": "terminal.run", "payload": {"command": res["command"], "exit_code": res["exit_code"]}}
    )
    await db.record_terminal_run(req.root, str(res["command"]), res["exit_code"])
    return TerminalRunResult(**res)


@router.post("/api/proc/start", dependencies=AUTH)
async def proc_start(req: ProcStartRequest) -> dict:
    try:
        mp = await process_manager.start(req.command, cwd=req.root, label=req.label or "")
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(400, f"cannot start: {exc}") from exc
    await asyncio.sleep(1.5)
    snap = mp.snapshot()
    await events.record(
        "process.started", label=snap["label"], process_id=mp.id, url=snap["url"], running=snap["running"]
    )
    return snap


@router.get("/api/proc/list", dependencies=AUTH)
async def proc_list() -> list[dict]:
    process_manager.prune()
    return [mp.snapshot(tail=0) for mp in process_manager.list()]


@router.get("/api/proc/{proc_id}/output", dependencies=AUTH)
async def proc_output(proc_id: str, tail: int = 200) -> dict:
    mp = process_manager.get(proc_id)
    if not mp:
        raise HTTPException(404, "unknown process")
    return mp.snapshot(tail=tail)


@router.post("/api/proc/stop", dependencies=AUTH)
async def proc_stop(req: ProcStopRequest) -> SimpleOk:
    ok = await process_manager.stop(req.process_id)
    return SimpleOk(ok=ok, detail="stopped" if ok else "unknown process")
