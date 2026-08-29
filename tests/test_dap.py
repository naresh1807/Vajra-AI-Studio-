"""DAP integration test against real debugpy."""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("debugpy")

from core.dap.manager import DapManager


async def test_breakpoint_stack_variables_continue(tmp_path):
    script = tmp_path / "prog.py"
    script.write_text(
        "def add(a, b):\n"
        "    total = a + b\n"      # line 2 - breakpoint
        "    return total\n"
        "\n"
        "print(add(2, 40))\n",
        encoding="utf-8",
    )
    mgr = DapManager()
    events: list[str] = []
    try:
        session = await mgr.start(
            str(tmp_path), "prog.py",
            breakpoints={str(script): [2]},
            on_event=lambda p: events.append(p["event"]) or asyncio.sleep(0),
        )
        # wait for the stop at the breakpoint
        for _ in range(60):
            await asyncio.sleep(0.3)
            if session.state == "stopped":
                break
        assert session.state == "stopped"
        # the stopped-event handler loads the stack asynchronously
        for _ in range(20):
            if session.frames:
                break
            await asyncio.sleep(0.2)
        assert session.frames and session.frames[0]["line"] == 2
        assert session.frames[0]["name"] == "add"

        variables = await session.variables()
        names = {v["name"]: v["value"] for v in variables}
        assert names.get("a") == "2" and names.get("b") == "40"

        ev = await session.evaluate("a + b")
        assert ev["result"] == "42"

        await session.continue_()
        for _ in range(30):
            await asyncio.sleep(0.3)
            if session.state == "terminated":
                break
        assert session.state == "terminated"
        assert "42" in "".join(session.output)
    finally:
        await mgr.shutdown_all()
