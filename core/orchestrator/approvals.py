"""In-memory approval gate. High-risk / elevated tool calls park here until a
client (Desktop / VS Code / Android) approves or rejects them.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Literal

Verdict = Literal["approved", "rejected"]


@dataclass
class PendingApproval:
    id: str
    goal_id: str
    task_id: str
    tool_name: str
    arguments: dict
    reason: str
    _event: asyncio.Event = field(default_factory=asyncio.Event)
    verdict: Verdict | None = None


class ApprovalGate:
    def __init__(self, default_timeout: float = 900.0) -> None:
        self._pending: dict[str, PendingApproval] = {}
        self._default_timeout = default_timeout

    def list_pending(self) -> list[PendingApproval]:
        return [p for p in self._pending.values() if p.verdict is None]

    def create(
        self, goal_id: str, task_id: str, tool_name: str, arguments: dict, reason: str
    ) -> PendingApproval:
        pa = PendingApproval(
            id=str(uuid.uuid4()),
            goal_id=goal_id,
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
            reason=reason,
        )
        self._pending[pa.id] = pa
        return pa

    def resolve(self, approval_id: str, verdict: Verdict) -> bool:
        pa = self._pending.get(approval_id)
        if not pa or pa.verdict is not None:
            return False
        pa.verdict = verdict
        pa._event.set()
        return True

    async def wait(self, approval_id: str, timeout: float | None = None) -> Verdict:
        pa = self._pending.get(approval_id)
        if not pa:
            return "rejected"
        try:
            await asyncio.wait_for(pa._event.wait(), timeout or self._default_timeout)
        except TimeoutError:
            pa.verdict = "rejected"
        return pa.verdict or "rejected"
