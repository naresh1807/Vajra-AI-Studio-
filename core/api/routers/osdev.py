"""OS-development agent — build + boot kernels/ISOs under QEMU."""

from __future__ import annotations

from fastapi import APIRouter

from core.api.deps import AUTH, osdev_agent, osdev_runs
from core.api.routers._runref import launch, status
from core.api.schemas import ComputerRunRequest, ComputerRunResult

router = APIRouter()


@router.get("/api/osdev/providers", dependencies=AUTH)
async def osdev_providers() -> dict:
    from core.osdev import providers_available

    return {"qemu": providers_available()}


@router.post("/api/osdev/run", dependencies=AUTH)
async def osdev_run(req: ComputerRunRequest) -> dict:
    return await launch(osdev_runs, "osd", osdev_agent, req.instruction)


@router.get("/api/osdev/runs/{run_id}", dependencies=AUTH)
async def osdev_run_status(run_id: str) -> ComputerRunResult:
    return status(osdev_runs, run_id, "osdev")
