"""API smoke tests with a stubbed model router (no network)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.llm import LLMResponse


class _StubRouter:
    def describe(self):
        return {"primary": "stub:stub", "fallback": "stub:stub"}

    async def complete(self, messages, tools=None, temperature=0.2, max_tokens=2048):
        return LLMResponse(text="stub reply", tool_calls=[], model="stub", provider="stub")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("VAJRA_DB_PATH", f"./data/api-test-{tmp_path.name}.db")
    import importlib

    import core.api.main as main

    importlib.reload(main)
    stub = _StubRouter()
    main.router = stub
    main.orchestrator.router = stub
    main.chat_agent.router = stub
    return TestClient(main.app), "test-token"


def test_health_no_auth(client):
    c, _ = client
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ping_requires_token(client):
    c, token = client
    assert c.get("/api/ping").status_code == 401
    assert c.get("/api/ping", headers={"X-Vajra-Token": token}).status_code == 200


def test_open_project_and_context(client, tmp_workspace):
    c, token = client
    h = {"X-Vajra-Token": token}
    r = c.post("/api/projects", json={"root_path": str(tmp_workspace)}, headers=h)
    assert r.status_code == 200
    pid = r.json()["id"]
    ctx = c.get(f"/api/projects/{pid}/context", headers=h)
    assert ctx.status_code == 200
    assert "python" in ctx.json()["profile"]["languages"]


def test_open_project_creates_folder(client, tmp_path):
    c, token = client
    h = {"X-Vajra-Token": token}
    newdir = str(tmp_path / "brand-new")
    assert c.post("/api/projects", json={"root_path": newdir}, headers=h).status_code == 400
    r = c.post("/api/projects", json={"root_path": newdir, "create": True}, headers=h)
    assert r.status_code == 200


def test_workspace_tree(client, tmp_workspace):
    c, token = client
    r = c.get("/api/workspace/tree", params={"root": str(tmp_workspace)}, headers={"X-Vajra-Token": token})
    assert r.status_code == 200
    names = [n["name"] for n in r.json()["children"]]
    assert "src" in names and "pyproject.toml" in names


def test_files_read_write_roundtrip(client, tmp_workspace):
    c, token = client
    h = {"X-Vajra-Token": token}
    w = c.post("/api/files/write", json={"root": str(tmp_workspace), "path": "notes/a.txt", "content": "hi"}, headers=h)
    assert w.status_code == 200 and w.json()["created"] is True
    r = c.post("/api/files/read", json={"root": str(tmp_workspace), "path": "notes/a.txt"}, headers=h)
    assert r.json()["content"] == "hi"


def test_files_write_rejects_escape(client, tmp_workspace):
    c, token = client
    r = c.post(
        "/api/files/write",
        json={"root": str(tmp_workspace), "path": "../evil.txt", "content": "x"},
        headers={"X-Vajra-Token": token},
    )
    assert r.status_code == 400


def test_terminal_run(client, tmp_workspace):
    c, token = client
    r = c.post(
        "/api/terminal/run",
        json={"root": str(tmp_workspace), "command": ["python", "-c", "print(6*7)"]},
        headers={"X-Vajra-Token": token},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["exit_code"] == 0 and body["stdout"].strip() == "42"


def test_proc_list_empty_and_authed(client):
    # ProcessManager lifecycle is covered directly in test_processes.py; here we
    # only check the route is wired and auth-gated (TestClient + Windows Proactor
    # subprocess transports don't share an event loop, so we don't spawn here).
    c, token = client
    assert c.get("/api/proc/list").status_code == 401
    assert c.get("/api/proc/list", headers={"X-Vajra-Token": token}).status_code == 200


def test_agent_chat(client):
    c, token = client
    r = c.post("/api/agent/chat", json={"message": "hi"}, headers={"X-Vajra-Token": token})
    assert r.status_code == 200 and r.json()["reply"] == "stub reply"


def test_mobile_page_served_unauthenticated(client):
    c, _ = client
    r = c.get("/mobile")
    assert r.status_code == 200
    assert "VAJRA" in r.text and "/api/computer/run" in r.text and "/api/approvals" in r.text
