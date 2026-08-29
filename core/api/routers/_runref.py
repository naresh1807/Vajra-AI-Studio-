"""Shared plumbing for the fire-and-forget agents (computer / osdev / security):
a background run that stores {status, reply, actions} in a dict."""

from __future__ import annotations

import asyncio

from fastapi import HTTPException

from core.api.deps import log, running
from core.api.schemas import ComputerRunResult


async def launch(store: dict, prefix: str, agent, instruction: str) -> dict:
    run_id = f"{prefix}-{len(store) + 1}-{id(instruction) % 100000}"
    store[run_id] = {"id": run_id, "status": "running", "reply": "", "actions": []}

    async def _go() -> None:
        try:
            res = await agent.run(run_id, instruction)
            store[run_id] = {
                "id": run_id, "status": "passed" if res.succeeded else "failed",
                "reply": res.reply, "actions": res.actions,
            }
        except Exception as exc:  # noqa: BLE001
            log.exception("%s run %s crashed", prefix, run_id)
            store[run_id] = {"id": run_id, "status": "failed", "reply": str(exc), "actions": []}

    running[run_id] = asyncio.create_task(_go())
    return {"id": run_id, "status": "running"}


def status(store: dict, run_id: str, kind: str) -> ComputerRunResult:
    data = store.get(run_id)
    if not data:
        raise HTTPException(404, f"unknown {kind} run")
    return ComputerRunResult(
        id=run_id, status=data.get("status", "running"), reply=data.get("reply", ""),
        actions=data.get("actions", []), succeeded=data.get("status") == "passed",
    )
