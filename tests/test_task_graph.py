from core.orchestrator.task_graph import Task, TaskGraph, TaskState


def _graph():
    a = Task(title="a", agent="git", instruction="checkpoint")
    b = Task(title="b", agent="coder", instruction="impl", depends_on=[a.id])
    c = Task(title="c", agent="tester", instruction="test", depends_on=[b.id])
    return TaskGraph(goal_id="g", goal="x", tasks=[a, b, c], max_retries=2), (a, b, c)


def test_dependency_ordering():
    g, (a, b, c) = _graph()
    assert g.next_ready_task().id == a.id
    g.mark_running(a)
    g.mark_passed(a)
    assert g.next_ready_task().id == b.id


def test_blocked_propagates():
    g, (a, b, c) = _graph()
    g.mark_running(a)
    g.mark_failed(a, "boom")  # retry 1
    g.mark_running(a)
    g.mark_failed(a, "boom")  # retry 2
    g.mark_running(a)
    disposition = g.mark_failed(a, "boom")  # exhausted
    assert disposition in ("replan", "blocked")
    assert g.next_ready_task() is None
    g._refresh_ready()
    assert b.state == TaskState.BLOCKED


def test_retry_budget():
    g, (a, _, _) = _graph()
    g.mark_running(a)
    assert g.mark_failed(a, "e") == "retry"
    assert a.state == TaskState.READY


def test_succeeded():
    g, (a, b, c) = _graph()
    for t in (a, b, c):
        g.mark_running(t)
        g.mark_passed(t)
    assert g.complete and g.succeeded
