"""Vajra Local API entrypoint.

Auth: every request (except /health) must present the pairing token via
`Authorization: Bearer <token>` or `X-Vajra-Token`. The token is a local shared
secret set at pairing time - this API binds to localhost by default.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.schemas import (
    ApproveRequest,
    ChatRequest,
    ChatResponse,
    CreateGoalRequest,
    GoalStatus,
    OpenProjectRequest,
    ProjectInfo,
    SimpleOk,
)
from core.config import get_settings
from core.events import EventBus
from core.llm import ChatMessage, ModelRouter
from core.orchestrator import Orchestrator
from core.orchestrator.approvals import ApprovalGate
from core.workspace import discover_workspace
from database import get_database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("vajra.api")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.persist_task = asyncio.create_task(_persist_events())
    log.info("Vajra Core up. models=%s", router.describe())
    try:
        yield
    finally:
        app.state.persist_task.cancel()


app = FastAPI(title="Vajra Local API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # localhost clients only; API is not publicly bound
    allow_methods=["*"],
    allow_headers=["*"],
)

events = EventBus(settings.log_dir)
approvals = ApprovalGate()
router = ModelRouter()
orchestrator = Orchestrator(events, approvals, settings, router)
db = get_database()
_running: dict[str, asyncio.Task] = {}


async def _persist_events() -> None:
    async for event in events.subscribe():
        with contextlib.suppress(Exception):
            await db.record_event(event.model_dump())
            if event.kind == "tool.result":
                p = event.payload
                await db.record_tool_call(
                    event.goal_id, event.task_id, p.get("tool"), p.get("success"), p.get("exit_code")
                )
                for path in p.get("changed_files", []) or []:
                    await db.record_file_change(event.goal_id, event.task_id, path)


def require_token(
    authorization: str | None = Header(default=None),
    x_vajra_token: str | None = Header(default=None),
) -> None:
    presented = None
    if authorization and authorization.lower().startswith("bearer "):
        presented = authorization.split(" ", 1)[1].strip()
    presented = presented or x_vajra_token
    if presented != settings.vajra_pairing_token:
        raise HTTPException(status_code=401, detail="invalid or missing pairing token")


# -- health / pairing -------------------------------------------------------
@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "vajra-core", "version": "0.1.0", "models": router.describe()}


@app.get("/api/v1/ping", dependencies=[Depends(require_token)])
async def ping() -> SimpleOk:
    return SimpleOk(detail="paired")


# -- projects -------------------------------------------------------------
@app.post("/api/v1/projects/open", dependencies=[Depends(require_token)])
async def open_project(req: OpenProjectRequest) -> ProjectInfo:
    profile = discover_workspace(req.root_path)
    name = req.name or profile.root.split("/")[-1].split("\\")[-1] or "project"
    pid = await db.upsert_project(name, str(profile.root), profile.model_dump())
    return ProjectInfo(id=pid, name=name, root_path=str(profile.root), profile=profile.model_dump())


@app.get("/api/v1/projects", dependencies=[Depends(require_token)])
async def list_projects() -> list[dict]:
    return await db.list_projects()


@app.get("/api/v1/projects/{project_id}/context", dependencies=[Depends(require_token)])
async def project_context(project_id: str) -> dict:
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "unknown project")
    import json

    return {"project": project, "profile": json.loads(project.get("profile_json") or "{}")}


# -- goals -------------------------------------------------------------
async def _run_goal(goal_id: str, text: str, workspace_root: str) -> None:
    await db.set_goal_status(goal_id, "running")
    try:
        result = await orchestrator.execute_goal(goal_id, text, workspace_root)
        await db.set_goal_status(goal_id, "passed" if result["succeeded"] else "failed")
    except Exception:  # noqa: BLE001
        log.exception("goal %s crashed", goal_id)
        await db.set_goal_status(goal_id, "failed")
    finally:
        _running.pop(goal_id, None)


@app.post("/api/v1/goals", dependencies=[Depends(require_token)])
async def create_goal(req: CreateGoalRequest) -> GoalStatus:
    workspace_root = req.workspace_root
    if not workspace_root and req.project_id:
        project = await db.get_project(req.project_id)
        workspace_root = project and project["root_path"]
    if not workspace_root:
        raise HTTPException(400, "workspace_root or a known project_id is required")

    goal_id = await db.create_goal(req.text, req.project_id)
    if req.autostart:
        _running[goal_id] = asyncio.create_task(_run_goal(goal_id, req.text, workspace_root))
    return GoalStatus(id=goal_id, text=req.text, status="running" if req.autostart else "pending")


@app.get("/api/v1/goals/{goal_id}", dependencies=[Depends(require_token)])
async def goal_status(goal_id: str) -> GoalStatus:
    goal = await db.get_goal(goal_id)
    if not goal:
        raise HTTPException(404, "unknown goal")
    graph = orchestrator.graph(goal_id)
    return GoalStatus(
        id=goal_id,
        text=goal["text"],
        status=goal["status"],
        progress=graph.progress() if graph else {},
        tasks=[t.model_dump() for t in graph.tasks] if graph else [],
        changed_files=await db.diff_for_goal(goal_id),
    )


@app.post("/api/v1/tasks/{goal_id}/cancel", dependencies=[Depends(require_token)])
async def cancel_goal(goal_id: str) -> SimpleOk:
    ok = orchestrator.cancel(goal_id)
    return SimpleOk(ok=ok, detail="cancellation requested" if ok else "goal not running")


@app.get("/api/v1/diff/{goal_id}", dependencies=[Depends(require_token)])
async def goal_diff(goal_id: str) -> dict:
    return {"goal_id": goal_id, "changed_files": await db.diff_for_goal(goal_id)}


# -- approvals -------------------------------------------------------
@app.get("/api/v1/approvals", dependencies=[Depends(require_token)])
async def list_approvals() -> list[dict]:
    return [
        {
            "id": p.id, "goal_id": p.goal_id, "task_id": p.task_id,
            "tool_name": p.tool_name, "reason": p.reason, "arguments": p.arguments,
        }
        for p in approvals.list_pending()
    ]


@app.post("/api/v1/tools/approve", dependencies=[Depends(require_token)])
async def approve(req: ApproveRequest) -> SimpleOk:
    verdict = "approved" if req.verdict == "approved" else "rejected"
    ok = approvals.resolve(req.approval_id, verdict)
    return SimpleOk(ok=ok, detail=verdict if ok else "unknown or already-resolved approval")


# -- chat -------------------------------------------------------
@app.post("/api/v1/chat", dependencies=[Depends(require_token)])
async def chat(req: ChatRequest) -> ChatResponse:
    resp = await router.complete(
        [
            ChatMessage(role="system", content="You are Vajra, a concise autonomous engineering assistant."),
            ChatMessage(role="user", content=req.message),
        ],
        max_tokens=800,
    )
    return ChatResponse(reply=resp.text, model=router.describe())


# -- event stream -------------------------------------------------------
@app.websocket("/api/v1/events")
async def events_ws(ws: WebSocket) -> None:
    token = ws.query_params.get("token")
    if token != settings.vajra_pairing_token:
        await ws.close(code=4401)
        return
    await ws.accept()
    try:
        async for event in events.subscribe():
            await ws.send_json(event.redacted())
    except WebSocketDisconnect:
        pass


def run() -> None:
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.vajra_host,
        port=settings.vajra_port,
        reload=False,
    )


if __name__ == "__main__":
    run()
