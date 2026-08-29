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

    import api.main as main

    importlib.reload(main)
    main.router = _StubRouter()
    main.orchestrator.router = _StubRouter()
    return TestClient(main.app), "test-token"


def test_health_no_auth(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ping_requires_token(client):
    c, token = client
    assert c.get("/api/v1/ping").status_code == 401
    assert c.get("/api/v1/ping", headers={"X-Vajra-Token": token}).status_code == 200


def test_open_project_and_context(client, tmp_workspace):
    c, token = client
    h = {"X-Vajra-Token": token}
    r = c.post("/api/v1/projects/open", json={"root_path": str(tmp_workspace)}, headers=h)
    assert r.status_code == 200
    pid = r.json()["id"]
    ctx = c.get(f"/api/v1/projects/{pid}/context", headers=h)
    assert ctx.status_code == 200
    assert "python" in ctx.json()["profile"]["languages"]


def test_chat(client):
    c, token = client
    r = c.post("/api/v1/chat", json={"message": "hi"}, headers={"X-Vajra-Token": token})
    assert r.status_code == 200 and r.json()["reply"] == "stub reply"
