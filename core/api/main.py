"""Vajra Local API — the secure localhost surface for Vajra AI Studio, Vajra
Mobile and the VS Code extension.

Auth: every /api/* request must present the pairing token via
`Authorization: Bearer <token>` or `X-Vajra-Token`. The token is a local shared
secret set at pairing time; the API binds to localhost by default.

Route map (manual v3.0 section 21):
    GET  /api/health
    GET  /api/projects              POST /api/projects
    GET  /api/projects/{id}/context
    GET  /api/workspace/tree
    POST /api/files/read            POST /api/files/write
    POST /api/editor/open
    POST /api/agent/chat            POST /api/agent/run     POST /api/agent/stop
    GET  /api/agent/runs/{id}       GET  /api/agent/runs/{id}/diff
    POST /api/terminal/run
    GET  /api/git/status            GET  /api/git/diff
    GET  /api/approvals             POST /api/approvals
    WS   /ws/events
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from core.agents.chat_agent import ChatAgent
from core.api.schemas import (
    AgentRunRequest,
    AgentRunStatus,
    AgentStopRequest,
    ApproveRequest,
    ChatRequest,
    ChatResponse,
    EditorOpenRequest,
    FileReadRequest,
    FileWriteRequest,
    GitRequest,
    OpenProjectRequest,
    ProjectInfo,
    SimpleOk,
    TerminalRunRequest,
    TerminalRunResult,
    TreeRequest,
)
from core.config import get_settings
from core.events import EventBus
from core.llm import ChatMessage, ModelRouter
from core.orchestrator import Orchestrator
from core.orchestrator.approvals import ApprovalGate
from core.tools import ToolContext
from core.tools.git_tools import GitDiffTool, GitStatusTool
from core.tools.process_tools import RunCommandTool
from core.workspace import WorkspaceError, build_tree, discover_workspace, read_file, write_file
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


app = FastAPI(title="Vajra Core API", version="0.2.0", lifespan=lifespan)
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
chat_agent = ChatAgent(router, orchestrator.registry)
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


AUTH = [Depends(require_token)]


# -- root / health -----------------------------------------------------
@app.get("/")
async def root() -> dict:
    return {
        "service": "vajra-core",
        "version": app.version,
        "docs": "/docs",
        "health": "/api/health",
        "hint": "all /api/* routes need an X-Vajra-Token or Authorization: Bearer header",
    }


@app.get("/api/health")
@app.get("/health")  # kept for the desktop sidecar's readiness probe
async def health() -> dict:
    return {"status": "ok", "service": "vajra-core", "version": app.version, "models": router.describe()}


@app.get("/api/ping", dependencies=AUTH)
async def ping() -> SimpleOk:
    return SimpleOk(detail="paired")


# -- projects --------------------------------------------------------
@app.post("/api/projects", dependencies=AUTH)
async def open_project(req: OpenProjectRequest) -> ProjectInfo:
    profile = discover_workspace(req.root_path)
    name = req.name or Path(profile.root).name or "project"
    pid = await db.upsert_project(name, profile.root, profile.model_dump())
    return ProjectInfo(id=pid, name=name, root_path=profile.root, profile=profile.model_dump())


@app.get("/api/projects", dependencies=AUTH)
async def list_projects() -> list[dict]:
    return await db.list_projects()


@app.get("/api/projects/{project_id}/context", dependencies=AUTH)
async def project_context(project_id: str) -> dict:
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(404, "unknown project")
    return {"project": project, "profile": json.loads(project.get("profile_json") or "{}")}


# -- workspace / files ---------------------------------------------
@app.get("/api/workspace/tree", dependencies=AUTH)
async def workspace_tree(root: str, max_depth: int = 6) -> dict:
    try:
        return build_tree(root, max_depth=max_depth).model_dump(exclude_none=True)
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/workspace/tree", dependencies=AUTH)
async def workspace_tree_post(req: TreeRequest) -> dict:
    return await workspace_tree(req.root, req.max_depth)


@app.post("/api/files/read", dependencies=AUTH)
async def files_read(req: FileReadRequest) -> dict:
    try:
        return read_file(req.root, req.path).model_dump()
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/files/write", dependencies=AUTH)
async def files_write(req: FileWriteRequest) -> dict:
    try:
        result = write_file(req.root, req.path, req.content)
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc
    await events.record(
        "tool.result", tool="write_file", success=True,
        changed_files=[req.path], exit_code=0,
    )
    await db.record_file_change(None, None, req.path)
    return result.model_dump()


@app.post("/api/editor/open", dependencies=AUTH)
async def editor_open(req: EditorOpenRequest) -> dict:
    """Editor-open is a UI concern; the Core just returns the file content."""
    try:
        return read_file(req.root, req.path).model_dump()
    except WorkspaceError as exc:
        raise HTTPException(400, str(exc)) from exc


# -- terminal -----------------------------------------------------
@app.post("/api/terminal/run", dependencies=AUTH)
async def terminal_run(req: TerminalRunRequest) -> TerminalRunResult:
    ctx = ToolContext(workspace_root=req.root)
    started = time.perf_counter()
    result = await RunCommandTool().run(
        ctx, command=req.command, timeout_seconds=req.timeout_seconds
    )
    argv = result.metadata.get("argv") or (
        req.command if isinstance(req.command, list) else [req.command]
    )
    await db.record_event(
        {"kind": "terminal.run", "payload": {"argv": argv, "exit_code": result.exit_code}}
    )
    return TerminalRunResult(
        stdout=result.stdout,
        stderr=result.stderr,
        exit_code=result.exit_code,
        duration_ms=int((time.perf_counter() - started) * 1000),
        cwd=req.root,
        command=argv,
    )


# -- git --------------------------------------------------------
@app.get("/api/git/status", dependencies=AUTH)
async def git_status(root: str) -> dict:
    result = await GitStatusTool().run(ToolContext(workspace_root=root))
    return {"success": result.success, "stdout": result.stdout, "stderr": result.stderr}


@app.get("/api/git/diff", dependencies=AUTH)
async def git_diff(root: str, path: str | None = None, staged: bool = False) -> dict:
    result = await GitDiffTool().run(
        ToolContext(workspace_root=root), path=path or "", staged=staged
    )
    return {"success": result.success, "diff": result.stdout, "stderr": result.stderr}


@app.post("/api/git/diff", dependencies=AUTH)
async def git_diff_post(req: GitRequest) -> dict:
    return await git_diff(req.root, req.path, req.staged)


# -- agent: chat --------------------------------------------------
@app.post("/api/agent/chat", dependencies=AUTH)
async def agent_chat(req: ChatRequest) -> ChatResponse:
    history = [ChatMessage(role=m.role, content=m.content) for m in req.history]
    history.append(ChatMessage(role="user", content=req.message))

    summary = ""
    if req.workspace_root:
        with contextlib.suppress(Exception):
            summary = orchestrator._summarize(discover_workspace(req.workspace_root))

    turn = await chat_agent.respond(history, req.workspace_root, summary)
    return ChatResponse(
        reply=turn.reply,
        tool_calls=turn.tool_calls,
        model={"provider": turn.provider, "model": turn.model, **router.describe()},
    )


# -- agent: run / stop / status --------------------------------
async def _run_goal(goal_id: str, text: str, workspace_root: str) -> None:
    await db.set_goal_status(goal_id, "running")
    try:
        result = await orchestrator.execute_goal(goal_id, text, workspace_root)
        await db.set_goal_status(goal_id, "passed" if result["succeeded"] else "failed")
    except Exception:  # noqa: BLE001
        log.exception("agent run %s crashed", goal_id)
        await db.set_goal_status(goal_id, "failed")
    finally:
        _running.pop(goal_id, None)


@app.post("/api/agent/run", dependencies=AUTH)
async def agent_run(req: AgentRunRequest) -> AgentRunStatus:
    workspace_root = req.workspace_root
    if not workspace_root and req.project_id:
        project = await db.get_project(req.project_id)
        workspace_root = project and project["root_path"]
    if not workspace_root:
        raise HTTPException(400, "workspace_root or a known project_id is required")

    goal_id = await db.create_goal(req.goal, req.project_id)
    if req.autostart:
        _running[goal_id] = asyncio.create_task(_run_goal(goal_id, req.goal, workspace_root))
    return AgentRunStatus(
        id=goal_id, goal=req.goal, status="running" if req.autostart else "pending"
    )


@app.get("/api/agent/runs/{run_id}", dependencies=AUTH)
async def agent_run_status(run_id: str) -> AgentRunStatus:
    goal = await db.get_goal(run_id)
    if not goal:
        raise HTTPException(404, "unknown run")
    graph = orchestrator.graph(run_id)
    return AgentRunStatus(
        id=run_id,
        goal=goal["text"],
        status=goal["status"],
        progress=graph.progress() if graph else {},
        tasks=[t.model_dump() for t in graph.tasks] if graph else [],
        changed_files=await db.diff_for_goal(run_id),
    )


@app.get("/api/agent/runs/{run_id}/diff", dependencies=AUTH)
async def agent_run_diff(run_id: str) -> dict:
    return {"run_id": run_id, "changed_files": await db.diff_for_goal(run_id)}


@app.post("/api/agent/stop", dependencies=AUTH)
async def agent_stop(req: AgentStopRequest) -> SimpleOk:
    ok = orchestrator.cancel(req.run_id)
    return SimpleOk(ok=ok, detail="stop requested" if ok else "run not active")


# -- approvals -------------------------------------------------
@app.get("/api/approvals", dependencies=AUTH)
async def list_approvals() -> list[dict]:
    return [
        {
            "id": p.id, "run_id": p.goal_id, "task_id": p.task_id,
            "tool_name": p.tool_name, "reason": p.reason, "arguments": p.arguments,
        }
        for p in approvals.list_pending()
    ]


@app.post("/api/approvals", dependencies=AUTH)
async def resolve_approval(req: ApproveRequest) -> SimpleOk:
    verdict = "approved" if req.verdict == "approved" else "rejected"
    ok = approvals.resolve(req.approval_id, verdict)
    return SimpleOk(ok=ok, detail=verdict if ok else "unknown or already-resolved approval")


# -- event stream ---------------------------------------------
@app.websocket("/ws/events")
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

    uvicorn.run("core.api.main:app", host=settings.vajra_host, port=settings.vajra_port, reload=False)


if __name__ == "__main__":
    run()
