"""Acceptance test #1 (IDE workflow), driven headlessly through the HTTP API:

    open project -> read a file -> ask Vajra to fix it -> review the diff ->
    accept (conflict-checked write) -> checkpoint -> a regression is introduced
    -> roll back to the checkpoint -> file is restored.

The model is stubbed so the chain itself is what's under test, not the LLM.
"""

from __future__ import annotations

import importlib
import subprocess

import pytest
from fastapi.testclient import TestClient

from core.agents.assist_agent import AssistResult


class _AssistStub:
    """Stands in for assist_agent: returns a fixed 'fixed' rewrite for `fix`."""

    def describe(self):
        return {"primary": "stub", "fallback": "stub"}

    async def run(self, *, action, path, file_content, selection=None, instruction=None, language=""):
        if action == "fix":
            new = file_content.replace("a + b", "a - b")
            return AssistResult(kind="edit", new_content=new, diff="--- a\n+++ b\n-a + b\n+a - b\n")
        return AssistResult(kind="prose", text="ok")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("VAJRA_DB_PATH", f"./data/e2e-{tmp_path.name}.db")
    import core.api.main as main

    importlib.reload(main)
    from core.api import deps

    deps.assist_agent = _AssistStub()
    monkeypatch.setattr("core.api.routers.assist.assist_agent", deps.assist_agent, raising=False)
    return TestClient(main.app), "test-token"


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_ide_fix_accept_checkpoint_rollback(client, tmp_path):
    c, token = client
    h = {"X-Vajra-Token": token}
    root = tmp_path / "proj"
    root.mkdir()
    (root / "calc.py").write_text("def sub(a, b):\n    return a + b\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")

    # open the project
    r = c.post("/api/projects", json={"root_path": str(root)}, headers=h)
    assert r.status_code == 200

    # read the file -> get its sha
    fc = c.post("/api/files/read", json={"root": str(root), "path": "calc.py"}, headers=h).json()
    assert "return a + b" in fc["content"]
    base_sha = fc["sha256"]

    # ask Vajra to fix it (bug: subtraction that adds)
    a = c.post(
        "/api/assist",
        json={"root": str(root), "path": "calc.py", "action": "fix"},
        headers=h,
    ).json()
    assert a["kind"] == "edit" and "return a - b" in a["new_content"]

    # accept -> conflict-checked write
    w = c.post(
        "/api/files/write",
        json={"root": str(root), "path": "calc.py", "content": a["new_content"], "base_sha": base_sha},
        headers=h,
    )
    assert w.status_code == 200

    # checkpoint the good state
    cp = c.post("/api/git/checkpoint", json={"root": str(root), "label": "good"}, headers=h)
    assert cp.status_code == 200
    tag = cp.json()["tag"]
    assert tag.startswith("vajra/")

    # a regression lands
    c.post(
        "/api/files/write",
        json={"root": str(root), "path": "calc.py", "content": "def sub(a, b):\n    return None\n"},
        headers=h,
    )
    assert "return None" in (root / "calc.py").read_text()

    # roll back to the checkpoint
    rb = c.post("/api/git/rollback", json={"root": str(root), "target": tag}, headers=h)
    assert rb.status_code == 200
    assert (root / "calc.py").read_text() == "def sub(a, b):\n    return a - b\n"
