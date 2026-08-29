"""Dependency-aware task DAG. A task runs only after its dependencies pass.
Failed tasks retry (bounded), then force a re-plan or escalate for approval.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["planner", "coder", "tester", "debugger", "reviewer", "git"]


class TaskState(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class Task(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str
    agent: AgentName
    instruction: str
    depends_on: list[str] = []
    success_criteria: str = ""
    state: TaskState = TaskState.PENDING
    attempts: int = 0
    last_error: str = ""
    result_summary: str = ""


class TaskGraph(BaseModel):
    goal_id: str
    goal: str
    tasks: list[Task] = []
    max_retries: int = 2

    def by_id(self, task_id: str) -> Task | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def _refresh_ready(self) -> None:
        for task in self.tasks:
            if task.state != TaskState.PENDING:
                continue
            deps = [self.by_id(d) for d in task.depends_on]
            if all(d and d.state == TaskState.PASSED for d in deps):
                task.state = TaskState.READY
            elif any(d and d.state in (TaskState.FAILED, TaskState.BLOCKED) for d in deps):
                task.state = TaskState.BLOCKED

    def next_ready_task(self) -> Task | None:
        self._refresh_ready()
        return next((t for t in self.tasks if t.state == TaskState.READY), None)

    def mark_running(self, task: Task) -> None:
        task.state = TaskState.RUNNING
        task.attempts += 1

    def mark_passed(self, task: Task, summary: str = "") -> None:
        task.state = TaskState.PASSED
        task.result_summary = summary

    def mark_failed(self, task: Task, error: str) -> Literal["retry", "replan", "blocked"]:
        task.last_error = error
        if task.attempts <= self.max_retries:
            task.state = TaskState.READY
            return "retry"
        task.state = TaskState.FAILED
        return "replan" if task.attempts <= self.max_retries + 2 else "blocked"

    @property
    def complete(self) -> bool:
        return all(
            t.state in (TaskState.PASSED, TaskState.SKIPPED, TaskState.BLOCKED, TaskState.FAILED)
            for t in self.tasks
        )

    @property
    def succeeded(self) -> bool:
        return bool(self.tasks) and all(
            t.state in (TaskState.PASSED, TaskState.SKIPPED) for t in self.tasks
        )

    def progress(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in self.tasks:
            counts[t.state.value] = counts.get(t.state.value, 0) + 1
        return counts
