from core.memory import WorkspaceMemory


def test_records_and_reads_back(tmp_path):
    m = WorkspaceMemory(tmp_path)
    m.record_decision("add a users table", "reviewer: APPROVED, schema is fine")
    m.record_known_error("test_subtract fails: returns a+b", "changed to a-b in calc.py")
    ctx = m.recent_context()
    assert "add a users table" in ctx
    assert "test_subtract fails" in ctx
    assert "changed to a-b" in ctx


def test_task_history_appends(tmp_path):
    m = WorkspaceMemory(tmp_path)
    m.record_task("goal one", "passed", ["a.py"])
    m.record_task("goal two", "failed", [])
    rows = m._read("task_history.jsonl")
    assert [r["goal"] for r in rows] == ["goal one", "goal two"]
    assert (tmp_path / ".vajra" / "task_history.jsonl").exists()


def test_empty_context(tmp_path):
    assert WorkspaceMemory(tmp_path).recent_context() == ""
