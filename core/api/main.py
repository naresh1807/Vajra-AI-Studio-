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

from core.agents.assist_agent import AssistAgent
from core.agents.chat_agent import ChatAgent
from core.api.schemas import (
    AgentRunRequest,
    AgentRunStatus,
    AgentStopRequest,
    ApproveRequest,
    AssistRequest,
    AssistResponse,
    ChatRequest,
    ChatResponse,
    EditorOpenRequest,
    FileReadRequest,
    FileWriteRequest,
    GitCheckpointRequest,
    GitCommitRequest,
    GitPathsRequest,
    GitRequest,
    GitRestoreRequest,
    LspRequest,
    OpenProjectRequest,
    ProcStartRequest,
    ProcStopRequest,
    ProjectInfo,
    SearchRequest,
    SimpleOk,
    TerminalRunRequest,
    TerminalRunResult,
    TreeRequest,
)
from core.config import get_settings
from core.events import EventBus
from core.llm import ChatMessage, ModelRouter
from core.lsp import lsp_manager
from core.lsp.config import supported as lsp_supported
from core.orchestrator import Orchestrator
from core.orchestrator.approvals import ApprovalGate
from core.runtime import git as gitsvc
from core.runtime import process_manager
from core.tools import ToolContext
from core.tools.process_tools import RunCommandTool
from core.workspace import (
    WorkspaceError,
    build_tree,
    discover_workspace,
    read_file,
    search_workspace,
    write_file,
)
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
        await process_manager.stop_all()
        await lsp_manager.shutdown_all()


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
assist_agent = AssistAgent(router)
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


# -- filesystem picker (directory browsing for "Open Folder") --------
@app.get("/api/fs/list", dependencies=AUTH)
async def fs_list(path: str = "") -> dict:
    """List sub-directories of `path` so a client can render a folder picker.
    Read-only, directories only, no file contents. Empty path -> drive roots
    (Windows) or filesystem root."""
    import os as _os
    import string as _string

    if not path:
        if _os.name == "nt":
            drives = [f"{d}:\\" for d in _string.ascii_uppercase if Path(f"{d}:\\").exists()]
            return {"path": "", "parent": None, "entries": [{"name": d, "path": d} for d in drives]}
        path = "/"

    base = Path(path).expanduser()
    if not base.is_dir():
        raise HTTPException(400, f"not a directory: {base}")
    base = base.resolve()
    entries = []
    try:
        for e in sorted(_os.scandir(base), key=lambda x: x.name.lower()):
            if e.name.startswith(".") or e.name in {"$RECYCLE.BIN", "System Volume Information"}:
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    entries.append({"name": e.name, "path": str(Path(e.path).resolve())})
            except OSError:
                continue
    except PermissionError as exc:
        raise HTTPException(403, f"permission denied: {base}") from exc
    parent = None if base.parent == base else str(base.parent)
    return {"path": str(base), "parent": parent, "entries": entries}


@app.post("/api/fs/mkdir", dependencies=AUTH)
async def fs_mkdir(req: OpenProjectRequest) -> dict:
    target = Path(req.root_path).expanduser()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(400, f"cannot create: {exc}") from exc
    return {"path": str(target.resolve())}


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


@app.post("/api/workspace/search", dependencies=AUTH)
async def workspace_search(req: SearchRequest) -> dict:
    hits = await asyncio.to_thread(
        search_workspace,
        req.root,
        req.query,
        is_regex=req.is_regex,
        case_sensitive=req.case_sensitive,
        glob=req.glob or "*",
        max_hits=req.max_hits,
    )
    return {"hits": [h.model_dump() for h in hits], "truncated": len(hits) >= req.max_hits}


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


# -- assisted coding ---------------------------------------------
@app.post("/api/assist", dependencies=AUTH)
async def assist(req: AssistRequest) -> AssistResponse:
    """Explain / fix / refactor / optimize / tests / document / security / edit.
    Edit actions return a *proposed* rewrite + diff; the client applies it via
    /api/files/write only after the user accepts (manual v3.0 sec 6)."""
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


# -- language server (diagnostics / hover / completion / definition) --
@app.get("/api/lsp/support", dependencies=AUTH)
async def lsp_support() -> dict:
    return {"languages": lsp_supported(), "servers": lsp_manager.status()}


@app.post("/api/lsp/diagnostics", dependencies=AUTH)
async def lsp_diagnostics(req: LspRequest) -> dict:
    client = await lsp_manager.sync(req.root, req.path, req.content, req.language)
    if not client:
        return {"supported": False, "diagnostics": []}
    for _ in range(8):  # give the server a moment to publish
        await asyncio.sleep(0.35)
        diags = client.diagnostics(req.path)
        if diags:
            break
    return {"supported": True, "diagnostics": client.diagnostics(req.path)}


@app.post("/api/lsp/completion", dependencies=AUTH)
async def lsp_completion(req: LspRequest) -> dict:
    client = await lsp_manager.sync(req.root, req.path, req.content, req.language)
    if not client:
        return {"supported": False, "items": []}
    await asyncio.sleep(0.1)
    items = await client.completion(req.path, req.line, req.character)
    return {"supported": True, "items": items[:200]}


@app.post("/api/lsp/hover", dependencies=AUTH)
async def lsp_hover(req: LspRequest) -> dict:
    client = await lsp_manager.sync(req.root, req.path, req.content, req.language)
    if not client:
        return {"supported": False, "value": None}
    await asyncio.sleep(0.1)
    return {"supported": True, "value": await client.hover(req.path, req.line, req.character)}


@app.post("/api/lsp/definition", dependencies=AUTH)
async def lsp_definition(req: LspRequest) -> dict:
    client = await lsp_manager.sync(req.root, req.path, req.content, req.language)
    if not client:
        return {"supported": False, "locations": []}
    await asyncio.sleep(0.1)
    return {"supported": True, "locations": await client.definition(req.path, req.line, req.character)}


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


# -- long-running processes (dev servers) --------------------
@app.post("/api/proc/start", dependencies=AUTH)
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


@app.get("/api/proc/list", dependencies=AUTH)
async def proc_list() -> list[dict]:
    process_manager.prune()
    return [mp.snapshot(tail=0) for mp in process_manager.list()]


@app.get("/api/proc/{proc_id}/output", dependencies=AUTH)
async def proc_output(proc_id: str, tail: int = 200) -> dict:
    mp = process_manager.get(proc_id)
    if not mp:
        raise HTTPException(404, "unknown process")
    return mp.snapshot(tail=tail)


@app.post("/api/proc/stop", dependencies=AUTH)
async def proc_stop(req: ProcStopRequest) -> SimpleOk:
    ok = await process_manager.stop(req.process_id)
    return SimpleOk(ok=ok, detail="stopped" if ok else "unknown process")


# -- git / source control -------------------------------------
@app.get("/api/git/status", dependencies=AUTH)
async def git_status(root: str) -> dict:
    st = await gitsvc.status(root)
    return {
        "is_repo": st.is_repo,
        "branch": st.branch,
        "ahead": st.ahead,
        "behind": st.behind,
        "files": [vars(f) for f in (st.files or [])],
    }


@app.get("/api/git/diff", dependencies=AUTH)
async def git_diff(root: str, path: str | None = None, staged: bool = False) -> dict:
    try:
        return {"diff": await gitsvc.diff(root, path, staged)}
    except gitsvc.GitError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/git/stage", dependencies=AUTH)
async def git_stage(req: GitPathsRequest) -> SimpleOk:
    await gitsvc.stage(req.root, req.paths)
    return SimpleOk()


@app.post("/api/git/unstage", dependencies=AUTH)
async def git_unstage(req: GitPathsRequest) -> SimpleOk:
    await gitsvc.unstage(req.root, req.paths)
    return SimpleOk()


@app.post("/api/git/discard", dependencies=AUTH)
async def git_discard(req: GitRequest) -> SimpleOk:
    if not req.path:
        raise HTTPException(400, "path required")
    await gitsvc.discard(req.root, req.path)
    return SimpleOk(detail=f"discarded {req.path}")


@app.post("/api/git/commit", dependencies=AUTH)
async def git_commit(req: GitCommitRequest) -> dict:
    try:
        sha = await gitsvc.commit(req.root, req.message)
    except gitsvc.GitError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "commit": sha}


@app.get("/api/git/checkpoints", dependencies=AUTH)
async def git_checkpoints(root: str) -> list[dict]:
    return await gitsvc.checkpoints(root)


@app.post("/api/git/checkpoint", dependencies=AUTH)
async def git_make_checkpoint(req: GitCheckpointRequest) -> dict:
    try:
        return await gitsvc.checkpoint(req.root, req.label)
    except gitsvc.GitError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/git/restore", dependencies=AUTH)
async def git_restore(req: GitRestoreRequest) -> SimpleOk:
    try:
        await gitsvc.restore(req.root, req.target)
    except gitsvc.GitError as exc:
        raise HTTPException(400, str(exc)) from exc
    await events.record("report", note=f"restored to {req.target}")
    return SimpleOk(detail=f"restored to {req.target}")


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
