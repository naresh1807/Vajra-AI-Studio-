"""P32: approval expiry, concurrent waiters, concurrent fire-and-forget runs."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from core.orchestrator.approvals import ApprovalGate


async def test_approval_expires_to_rejected():
    gate = ApprovalGate(default_timeout=900)
    pa = gate.create("g", "t", "run_powershell", {}, "risky")
    verdict = await gate.wait(pa.id, timeout=0.05)
    assert verdict == "rejected"
    assert gate.resolve(pa.id, "approved") is False  # already resolved


async def test_two_concurrent_approvals_are_independent():
    gate = ApprovalGate()
    a = gate.create("g", "t1", "x", {}, "a")
    b = gate.create("g", "t2", "y", {}, "b")
    assert {p.id for p in gate.list_pending()} == {a.id, b.id}

    task_a = asyncio.create_task(gate.wait(a.id, timeout=5))
    task_b = asyncio.create_task(gate.wait(b.id, timeout=5))
    await asyncio.sleep(0.01)
    gate.resolve(a.id, "approved")
    assert await task_a == "approved"
    assert not task_b.done()
    gate.resolve(b.id, "rejected")
    assert await task_b == "rejected"


async def test_concurrent_fire_and_forget_runs():
    from core.api.routers import _runref

    store: dict = {}
    started = asyncio.Event()

    class _Agent:
        def __init__(self, tag):
            self.tag = tag

        async def run(self, run_id, instruction):
            started.set()
            await asyncio.sleep(0.05)

            class R:
                succeeded = True
                reply = f"{self.tag}:{instruction}"
                actions: list = []

            return R()

    r1 = await _runref.launch(store, "t", _Agent("one"), "do A")
    r2 = await _runref.launch(store, "t", _Agent("two"), "do B")
    assert r1["id"] != r2["id"]
    await asyncio.sleep(0.15)
    assert _runref.status(store, r1["id"], "t").status == "passed"
    assert _runref.status(store, r2["id"], "t").status == "passed"
    with pytest.raises(HTTPException):
        _runref.status(store, "nope", "t")
