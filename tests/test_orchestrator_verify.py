"""Unit tests for the orchestrator's structural verification and graph flow."""

from core.orchestrator.orchestrator import Orchestrator
from core.orchestrator.task_graph import Task, TaskGraph, TaskState

V = Orchestrator._verify


def _task(agent: str) -> Task:
    return Task(title="t", agent=agent, instruction="i")


def test_infra_error_always_fails():
    ok, reason = V(_task("coder"), None, "policy blocked run_command", False)
    assert not ok and reason == "policy blocked run_command"


def test_tester_needs_a_check_to_have_run():
    assert V(_task("tester"), None, None, False)[0] is False
    assert V(_task("tester"), True, None, False)[0] is True
    # a RED test is NOT a task failure - it's surfaced separately
    assert V(_task("tester"), False, None, False)[0] is True


def test_coder_debugger_git_pass_without_infra_error():
    for agent in ("coder", "debugger", "git"):
        assert V(_task(agent), None, None, True)[0] is True


def test_reviewer_is_non_blocking():
    assert V(_task("reviewer"), None, None, False)[0] is True


def test_skipped_dependency_unblocks_dependents():
    a = Task(title="a", agent="tester", instruction="i")
    b = Task(title="b", agent="coder", instruction="i", depends_on=[a.id])
    g = TaskGraph(goal_id="g", goal="x", tasks=[a, b])
    a.state = TaskState.SKIPPED
    assert g.next_ready_task().id == b.id


def test_failed_dependency_blocks_dependents():
    a = Task(title="a", agent="tester", instruction="i")
    b = Task(title="b", agent="coder", instruction="i", depends_on=[a.id])
    g = TaskGraph(goal_id="g", goal="x", tasks=[a, b])
    a.state = TaskState.FAILED
    assert g.next_ready_task() is None
    g._refresh_ready()
    assert b.state == TaskState.BLOCKED


# -- activity feed (Claude-Code-style transparency) -------------------
def _orch():
    from core.events import EventBus
    from core.orchestrator.approvals import ApprovalGate
    return Orchestrator(EventBus("./logs"), ApprovalGate())


def test_describe_tool_is_human_readable():
    from core.orchestrator.orchestrator import _describe_tool
    assert _describe_tool("write_file", {"path": "lib/main.dart"}) == "Writing lib/main.dart"
    assert _describe_tool("run_command", {"command": ["flutter", "create", "."]}) == "Running: flutter create ."
    assert _describe_tool("patch_file", {"path": "a.py"}) == "Editing a.py"
    assert "bluetooth" in _describe_tool("semantic_search", {"query": "bluetooth"})


def test_clean_reasoning_drops_tool_json():
    from core.orchestrator.orchestrator import _clean_reasoning
    assert _clean_reasoning("I'll create the pubspec.\n\n{...}") == "I'll create the pubspec."
    assert _clean_reasoning('{"tool": "x"}') == ""
    assert _clean_reasoning("") == ""


def test_activity_feed_notes_and_paging():
    orch = _orch()
    orch._note("g1", "goal", "Goal: build an app")
    orch._note("g1", "action", "Writing lib/main.dart")
    orch._note("g1", "result", "✓ lib/main.dart")
    feed = orch.activity("g1")
    assert [a["kind"] for a in feed] == ["goal", "action", "result"]
    assert feed[1]["text"] == "Writing lib/main.dart"
    # paging by id returns only newer items
    after = orch.activity("g1", since=feed[1]["i"])
    assert [a["kind"] for a in after] == ["action", "result"]
    assert orch.activity("g1", since=feed[-1]["i"] + 1) == []
