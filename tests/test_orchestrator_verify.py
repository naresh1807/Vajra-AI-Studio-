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
