"""High-risk action approvals + the event stream WebSocket."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.api.deps import AUTH, approvals, authenticates, events
from core.api.schemas import ApproveRequest, SimpleOk

router = APIRouter()


@router.get("/api/approvals", dependencies=AUTH)
async def list_approvals() -> list[dict]:
    return [
        {"id": p.id, "run_id": p.goal_id, "task_id": p.task_id,
         "tool_name": p.tool_name, "reason": p.reason, "arguments": p.arguments}
        for p in approvals.list_pending()
    ]


@router.post("/api/approvals", dependencies=AUTH)
async def resolve_approval(req: ApproveRequest) -> SimpleOk:
    verdict = "approved" if req.verdict == "approved" else "rejected"
    ok = approvals.resolve(req.approval_id, verdict)
    return SimpleOk(ok=ok, detail=verdict if ok else "unknown or already-resolved approval")


@router.websocket("/ws/events")
async def events_ws(ws: WebSocket) -> None:
    if not authenticates(ws.query_params.get("token")):
        await ws.close(code=4401)
        return
    await ws.accept()
    try:
        async for event in events.subscribe():
            await ws.send_json(event.redacted())
    except WebSocketDisconnect:
        pass
