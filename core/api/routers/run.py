"""Run / Build the project (master-prompt P14)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException

from core.api.deps import AUTH, events
from core.runtime import process_manager
from core.runtime import runner as runsvc
from core.runtime import terminal as termsvc

router = APIRouter()


@router.get("/api/run/plan", dependencies=AUTH)
async def run_plan(root: str, kind: str = "run") -> dict:
    p = runsvc.plan(root, kind)
    return {
        "command": p.command, "cwd": p.cwd, "framework": p.framework,
        "port": p.port, "kind": p.kind, "alternatives": p.alternatives,
    }


@router.post("/api/run/start", dependencies=AUTH)
async def run_start(body: dict) -> dict:
    root = str(body.get("root", ""))
    kind = str(body.get("kind", "run"))
    command = str(body.get("command", "")) or runsvc.plan(root, kind).command
    if not command:
        raise HTTPException(400, "no run command could be determined - pass `command`")

    if kind in ("build", "test"):
        # one-shot: run to completion, return output
        res = await termsvc.run_terminal(root, command, timeout_seconds=1800)
        await events.record("report", note=f"{kind}: `{command}` exit {res['exit_code']}")
        return {"kind": kind, "command": command, **res}

    # a server: start it detached (through the shell) and report the URL
    mp = await process_manager.start(command, cwd=root, label=command, shell=True)
    await asyncio.sleep(1.5)
    snap = mp.snapshot()
    await events.record("process.started", label=snap["label"], process_id=mp.id, url=snap["url"])
    return {"kind": "run", "command": command, **snap}
