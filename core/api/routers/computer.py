"""Computer agent — acts outside the workspace, approval-gated."""

from __future__ import annotations

from fastapi import APIRouter

from core.api.deps import AUTH, computer_agent, computer_runs
from core.api.routers._runref import launch, status
from core.api.schemas import ComputerRunRequest, ComputerRunResult

router = APIRouter()


@router.post("/api/computer/run", dependencies=AUTH)
async def computer_run(req: ComputerRunRequest) -> dict:
    return await launch(computer_runs, "cmp", computer_agent, req.instruction)


@router.get("/api/computer/runs/{run_id}", dependencies=AUTH)
async def computer_run_status(run_id: str) -> ComputerRunResult:
    return status(computer_runs, run_id, "computer")
