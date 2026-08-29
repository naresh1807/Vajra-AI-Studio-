"""Test explorer: discover + run."""

from __future__ import annotations

from fastapi import APIRouter

from core.api.deps import AUTH, events
from core.api.schemas import TestDiscoverRequest, TestRunRequest
from core.runtime import testing as testsvc

router = APIRouter()


@router.post("/api/testing/discover", dependencies=AUTH)
async def testing_discover(req: TestDiscoverRequest) -> dict:
    return await testsvc.discover(req.root)


@router.post("/api/testing/run", dependencies=AUTH)
async def testing_run(req: TestRunRequest) -> dict:
    run = await testsvc.run_tests(req.root, req.node_ids or None)
    await events.record(
        "report", note=f"tests: {run.framework} {'ok' if run.ok else 'failed'} {run.totals}"
    )
    return run.as_dict()
