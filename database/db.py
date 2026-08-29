"""Thin SQLite wrapper + repositories. One connection guarded by a lock is fine
for a personal local Core; swap the internals for asyncpg later without changing
callers.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.config import get_settings

_SCHEMA = Path(__file__).with_name("schema.sql")


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._lock = asyncio.Lock()
        self._conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
        self._conn.commit()

    async def _write(self, sql: str, params: tuple = ()) -> None:
        async with self._lock:
            self._conn.execute(sql, params)
            self._conn.commit()

    async def _query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        async with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    # -- projects ---------------------------------------------------------
    async def upsert_project(self, name: str, root_path: str, profile: dict | None = None) -> str:
        existing = await self._query("SELECT id FROM projects WHERE root_path = ?", (root_path,))
        if existing:
            pid = existing[0]["id"]
            await self._write(
                "UPDATE projects SET name = ?, profile_json = ? WHERE id = ?",
                (name, json.dumps(profile or {}), pid),
            )
            return pid
        pid = str(uuid.uuid4())
        await self._write(
            "INSERT INTO projects (id, name, root_path, profile_json, created_at) VALUES (?,?,?,?,?)",
            (pid, name, root_path, json.dumps(profile or {}), time.time()),
        )
        return pid

    async def get_project(self, project_id: str) -> dict | None:
        rows = await self._query("SELECT * FROM projects WHERE id = ?", (project_id,))
        return rows[0] if rows else None

    async def list_projects(self) -> list[dict]:
        return await self._query("SELECT * FROM projects ORDER BY created_at DESC")

    # -- goals ----------------------------------------------------------
    async def create_goal(self, text: str, project_id: str | None) -> str:
        gid = str(uuid.uuid4())
        now = time.time()
        await self._write(
            "INSERT INTO goals (id, project_id, text, status, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (gid, project_id, text, "pending", now, now),
        )
        return gid

    async def set_goal_status(self, goal_id: str, status: str) -> None:
        await self._write(
            "UPDATE goals SET status = ?, updated_at = ? WHERE id = ?",
            (status, time.time(), goal_id),
        )

    async def get_goal(self, goal_id: str) -> dict | None:
        rows = await self._query("SELECT * FROM goals WHERE id = ?", (goal_id,))
        return rows[0] if rows else None

    # -- audit --------------------------------------------------------
    async def record_event(self, event: dict) -> None:
        await self._write(
            "INSERT INTO audit_events (id, kind, goal_id, task_id, payload_json, ts) VALUES (?,?,?,?,?,?)",
            (
                event.get("id", str(uuid.uuid4())),
                event.get("kind", "event"),
                event.get("goal_id"),
                event.get("task_id"),
                json.dumps(event.get("payload", {})),
                event.get("ts", time.time()),
            ),
        )

    async def record_tool_call(self, goal_id, task_id, tool_name, success, exit_code) -> None:
        await self._write(
            "INSERT INTO tool_calls (id, goal_id, task_id, tool_name, success, exit_code, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), goal_id, task_id, tool_name, int(bool(success)), exit_code, time.time()),
        )

    async def record_file_change(self, goal_id, task_id, path) -> None:
        await self._write(
            "INSERT INTO file_changes (goal_id, task_id, path, created_at) VALUES (?,?,?,?)",
            (goal_id, task_id, path, time.time()),
        )

    async def record_indexed_files(self, root: str, paths: list[str]) -> None:
        now = time.time()
        rows = [(root, p, now) for p in paths[:8000]]
        for i in range(0, len(rows), 500):
            await self._write(
                "INSERT OR REPLACE INTO project_files (root, path, indexed_at) VALUES "
                + ",".join(["(?,?,?)"] * len(rows[i : i + 500])),
                tuple(v for row in rows[i : i + 500] for v in row),
            )

    async def record_memory(self, root: str, kind: str, content: str) -> None:
        await self._write(
            "INSERT INTO memories (root, kind, content, created_at) VALUES (?,?,?,?)",
            (root, kind, content, time.time()),
        )

    async def record_terminal_run(self, root: str | None, command: str, exit_code: int | None) -> None:
        await self._write(
            "INSERT INTO terminal_runs (root, command, exit_code, created_at) VALUES (?,?,?,?)",
            (root, command, exit_code, time.time()),
        )

    async def diff_for_goal(self, goal_id: str) -> list[str]:
        rows = await self._query(
            "SELECT DISTINCT path FROM file_changes WHERE goal_id = ? ORDER BY path", (goal_id,)
        )
        return [r["path"] for r in rows]

    def close(self) -> None:
        self._conn.close()


@lru_cache
def get_database() -> Database:
    return Database(get_settings().db_path)
