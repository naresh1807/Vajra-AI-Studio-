"""Autonomous agent: chat, run, status, diff, stop."""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, HTTPException

from core.api.deps import AUTH, chat_agent, db, log, model_router, orchestrator, running
from core.api.schemas import (
    AgentRunRequest,
    AgentRunStatus,
    AgentStopRequest,
    ChatRequest,
    ChatResponse,
    SimpleOk,
)
from core.llm import ChatMessage
from core.workspace import discover_workspace

router = APIRouter()


@router.post("/api/agent/chat", dependencies=AUTH)
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
        model={"provider": turn.provider, "model": turn.model, **model_router.describe()},
    )


async def _run_goal(goal_id: str, text: str, workspace_root: str, focus: str = "") -> None:
    await db.set_goal_status(goal_id, "running")
    try:
        result = await orchestrator.execute_goal(goal_id, text, workspace_root, focus=focus)
        await db.set_goal_status(goal_id, "passed" if result["succeeded"] else "failed")
    except Exception:  # noqa: BLE001
        log.exception("agent run %s crashed", goal_id)
        await db.set_goal_status(goal_id, "failed")
    finally:
        running.pop(goal_id, None)


@router.post("/api/agent/run", dependencies=AUTH)
async def agent_run(req: AgentRunRequest) -> AgentRunStatus:
    workspace_root = req.workspace_root
    if not workspace_root and req.project_id:
        project = await db.get_project(req.project_id)
        workspace_root = project and project["root_path"]
    if not workspace_root:
        raise HTTPException(400, "workspace_root or a known project_id is required")
    goal_id = await db.create_goal(req.goal, req.project_id)
    if req.autostart:
        running[goal_id] = asyncio.create_task(
            _run_goal(goal_id, req.goal, workspace_root, req.focus)
        )
    return AgentRunStatus(id=goal_id, goal=req.goal, status="running" if req.autostart else "pending")


@router.get("/api/agent/runs/{run_id}", dependencies=AUTH)
async def agent_run_status(run_id: str) -> AgentRunStatus:
    goal = await db.get_goal(run_id)
    if not goal:
        raise HTTPException(404, "unknown run")
    graph = orchestrator.graph(run_id)
    return AgentRunStatus(
        id=run_id, goal=goal["text"], status=goal["status"],
        progress=graph.progress() if graph else {},
        tasks=[t.model_dump() for t in graph.tasks] if graph else [],
        changed_files=await db.diff_for_goal(run_id),
    )


@router.get("/api/agent/runs/{run_id}/diff", dependencies=AUTH)
async def agent_run_diff(run_id: str) -> dict:
    return {"run_id": run_id, "changed_files": await db.diff_for_goal(run_id)}


@router.post("/api/agent/stop", dependencies=AUTH)
async def agent_stop(req: AgentStopRequest) -> SimpleOk:
    ok = orchestrator.cancel(req.run_id)
    return SimpleOk(ok=ok, detail="stop requested" if ok else "run not active")


@router.get("/api/agent/interrupted", dependencies=AUTH)
async def agent_interrupted() -> dict:
    """Runs that were mid-flight when the Core last stopped (P30 crash recovery).
    The client offers: review changes / rollback to the checkpoint / discard."""
    out = []
    for g in await db.interrupted_goals():
        out.append({
            "id": g["id"], "goal": g["text"], "updated_at": g["updated_at"],
            "changed_files": await db.diff_for_goal(g["id"]),
        })
    return {"interrupted": out}
