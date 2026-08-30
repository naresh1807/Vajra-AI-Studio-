"""P30: a run left 'running' when the Core stopped is recovered as 'interrupted'."""

from __future__ import annotations

import pytest

from database.db import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "cr.db")


async def test_running_goal_becomes_interrupted(db):
    gid = await db.create_goal("fix the build", None)
    await db.set_goal_status(gid, "running")
    await db.record_file_change(gid, None, "src/app.py")

    stale = await db.mark_interrupted_goals()
    assert [g["id"] for g in stale] == [gid]
    assert (await db.get_goal(gid))["status"] == "interrupted"

    rows = await db.interrupted_goals()
    assert rows and rows[0]["id"] == gid
    assert await db.diff_for_goal(gid) == ["src/app.py"]

    # a completed goal is untouched
    done = await db.create_goal("done", None)
    await db.set_goal_status(done, "passed")
    await db.mark_interrupted_goals()
    assert (await db.get_goal(done))["status"] == "passed"
