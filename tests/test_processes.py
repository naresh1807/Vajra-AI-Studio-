import asyncio
import sys

from core.runtime.processes import ProcessManager


async def test_start_read_stop(tmp_path):
    pm = ProcessManager()
    mp = await pm.start(
        [sys.executable, "-u", "-c", "print('server on http://localhost:5173'); import time; time.sleep(30)"],
        cwd=str(tmp_path),
        label="fake dev server",
    )
    await asyncio.sleep(1.0)
    snap = mp.snapshot()
    assert snap["running"] is True
    assert "http://localhost:5173" in snap["output"]
    assert mp.url == "http://localhost:5173"

    assert await pm.stop(mp.id) is True
    await asyncio.sleep(0.2)
    assert mp.running is False


async def test_stop_unknown():
    pm = ProcessManager()
    assert await pm.stop("nope") is False


async def test_exited_process_reports_exit_code(tmp_path):
    pm = ProcessManager()
    mp = await pm.start([sys.executable, "-c", "raise SystemExit(3)"], cwd=str(tmp_path))
    await asyncio.sleep(0.6)
    snap = mp.snapshot()
    assert snap["running"] is False
    assert snap["exit_code"] == 3
    await pm.stop_all()
