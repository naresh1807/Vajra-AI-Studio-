"""Debug Adapter Protocol (Python via debugpy)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.api.deps import AUTH, events
from core.api.schemas import (
    DebugActionRequest,
    DebugBreakpointsRequest,
    DebugEvalRequest,
    DebugStartRequest,
    SimpleOk,
)
from core.dap import dap_manager

router = APIRouter()


@router.post("/api/debug/start", dependencies=AUTH)
async def debug_start(req: DebugStartRequest) -> dict:
    async def relay(payload: dict) -> None:
        await events.record("dap.event", **{k: v for k, v in payload.items() if k != "type"})

    try:
        session = await dap_manager.start(
            req.root, req.program, req.args, req.breakpoints, on_event=relay
        )
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(400, f"cannot start debugger: {exc}") from exc
    return session.snapshot()


@router.get("/api/debug/sessions", dependencies=AUTH)
async def debug_sessions() -> list[dict]:
    return [s.snapshot() for s in dap_manager.list()]


@router.get("/api/debug/state/{session_id}", dependencies=AUTH)
async def debug_state(session_id: str) -> dict:
    session = dap_manager.get(session_id)
    if not session:
        raise HTTPException(404, "unknown debug session")
    snap = session.snapshot()
    if session.state == "stopped":
        snap["variables"] = await session.variables()
    return snap


@router.post("/api/debug/action", dependencies=AUTH)
async def debug_action(req: DebugActionRequest) -> SimpleOk:
    session = dap_manager.get(req.session_id)
    if not session:
        raise HTTPException(404, "unknown debug session")
    fn = {
        "continue": session.continue_, "next": session.next, "step_in": session.step_in,
        "step_out": session.step_out, "pause": session.pause,
    }.get(req.action)
    if not fn:
        raise HTTPException(400, f"unknown action: {req.action}")
    await fn()
    return SimpleOk(detail=req.action)


@router.post("/api/debug/breakpoints", dependencies=AUTH)
async def debug_breakpoints(req: DebugBreakpointsRequest) -> dict:
    session = dap_manager.get(req.session_id)
    if not session:
        raise HTTPException(404, "unknown debug session")
    return {"breakpoints": await session.set_breakpoints(req.path, req.lines)}


@router.post("/api/debug/evaluate", dependencies=AUTH)
async def debug_evaluate(req: DebugEvalRequest) -> dict:
    session = dap_manager.get(req.session_id)
    if not session:
        raise HTTPException(404, "unknown debug session")
    return await session.evaluate(req.expression)


@router.post("/api/debug/stop/{session_id}", dependencies=AUTH)
async def debug_stop(session_id: str) -> SimpleOk:
    ok = await dap_manager.stop(session_id)
    return SimpleOk(ok=ok, detail="stopped" if ok else "unknown session")
