"""Append-only workspace memory under .vajra/. Deterministic, local, no secrets.

RAG / embeddings land in Phase 5; for now this is the durable project log the
manual describes: decisions, task history, known recurring errors.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class WorkspaceMemory:
    def __init__(self, root: str | Path) -> None:
        self.dir = Path(root) / ".vajra"
        self.dir.mkdir(exist_ok=True)

    def _append(self, name: str, record: dict[str, Any]) -> None:
        record = {"ts": time.time(), **record}
        with (self.dir / name).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read(self, name: str, limit: int | None = None) -> list[dict[str, Any]]:
        path = self.dir / name
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        return rows[-limit:] if limit else rows

    def record_decision(self, summary: str, rationale: str = "") -> None:
        self._append("decisions.jsonl", {"summary": summary, "rationale": rationale})

    def record_task(self, goal: str, status: str, files_changed: list[str]) -> None:
        self._append(
            "task_history.jsonl",
            {"goal": goal, "status": status, "files_changed": files_changed},
        )

    def record_known_error(self, signature: str, fix: str) -> None:
        self._append("known_errors.jsonl", {"signature": signature, "fix": fix})

    def recent_context(self) -> str:
        parts: list[str] = []
        decisions = self._read("decisions.jsonl", limit=8)
        if decisions:
            parts.append("Recent decisions:\n" + "\n".join(f"- {d['summary']}" for d in decisions))
        errors = self._read("known_errors.jsonl", limit=8)
        if errors:
            parts.append(
                "Known recurring errors:\n"
                + "\n".join(f"- {e['signature']} -> {e['fix']}" for e in errors)
            )
        return "\n\n".join(parts)
