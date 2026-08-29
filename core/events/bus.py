"""In-process async event bus + structured JSONL logging.

Every plan, tool call, patch, command, test and retry emits a VajraEvent so the
Desktop / VS Code / Android clients can stream progress and so we keep an audit
trail on disk. Secrets are redacted before anything is persisted.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

EventKind = Literal[
    "goal.created",
    "plan.created",
    "task.started",
    "task.updated",
    "task.completed",
    "task.failed",
    "agent.action",
    "tool.call",
    "tool.result",
    "approval.requested",
    "approval.resolved",
    "model.request",
    "terminal.run",
    "process.started",
    "process.stopped",
    "file.written",
    "error",
    "report",
]

_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|bearer|token|password|secret|private[_-]?key)"
    r'["\':=\s]+([A-Za-z0-9._\-/+]{8,})'
)


def redact(value: Any) -> Any:
    """Recursively redact secret-looking values before persistence."""
    if isinstance(value, str):
        return _SECRET_RE.sub(r"\1=***REDACTED***", value)
    if isinstance(value, dict):
        return {
            k: ("***REDACTED***" if _SECRET_RE.search(f"{k}=x") else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class VajraEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ts: float = Field(default_factory=time.time)
    kind: EventKind
    goal_id: str | None = None
    task_id: str | None = None
    payload: dict[str, Any] = {}

    def redacted(self) -> dict[str, Any]:
        data = self.model_dump()
        data["payload"] = redact(data["payload"])
        return data


class EventBus:
    """Fan-out bus. Subscribers get an async queue; all events also append to audit.jsonl."""

    def __init__(self, log_dir: Path | str) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._subscribers: set[asyncio.Queue[VajraEvent]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: VajraEvent) -> None:
        line = json.dumps(event.redacted(), ensure_ascii=False)
        async with self._lock:
            with (self._log_dir / "task_events.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        for q in list(self._subscribers):
            q.put_nowait(event)

    async def record(self, kind: EventKind, **payload: Any) -> VajraEvent:
        goal_id = payload.pop("goal_id", None)
        task_id = payload.pop("task_id", None)
        event = VajraEvent(kind=kind, goal_id=goal_id, task_id=task_id, payload=payload)
        await self.publish(event)
        return event

    async def subscribe(self) -> AsyncIterator[VajraEvent]:
        q: asyncio.Queue[VajraEvent] = asyncio.Queue()
        self._subscribers.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)
