"""P35/P36: environment diagnostics + first-run wizard state."""

from __future__ import annotations

import importlib

import pytest

from core.runtime.doctor import Check, run_doctor


async def test_run_doctor_shape():
    d = await run_doctor()
    assert set(d) == {"ok", "checks"}
    names = {c["name"] for c in d["checks"]}
    assert {"Python", "Git", "Model API"} <= names
    for c in d["checks"]:
        assert c["status"] in ("ok", "missing", "error")
    # required tools (python, git) present in this env -> overall ok
    assert d["ok"] is True


async def test_optional_missing_does_not_fail_overall():
    checks = [
        Check("Python", "ok", required=True),
        Check("Git", "ok", required=True),
        Check("Flutter", "missing", required=False),
        Check("Docker", "missing", required=False),
    ]
    assert all(c.status == "ok" for c in checks if c.required)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("VAJRA_DB_PATH", f"./data/setup-test-{tmp_path.name}.db")
    monkeypatch.setenv("VAJRA_PAIRING_TOKEN", "test-token")
    import core.api.routers.setup as setup_mod

    monkeypatch.setattr(setup_mod, "_STATE", tmp_path / "setup.json")
    import core.api.main as main

    importlib.reload(main)
    from fastapi.testclient import TestClient

    return TestClient(main.app), "test-token"


def test_setup_flow(client):
    c, token = client
    h = {"X-Vajra-Token": token}

    hr = c.get("/api/setup/health", headers=h)
    assert hr.status_code == 200 and isinstance(hr.json()["checks"], list)

    st = c.get("/api/setup/state", headers=h).json()
    assert st["completed"] is False and st["device_id"].startswith("vajra-")

    done = c.post("/api/setup/complete", json={"workspace": str(client), "model": {"primary": "x"}}, headers=h)
    assert done.status_code == 200 and done.json()["ok"] is True

    st2 = c.get("/api/setup/state", headers=h).json()
    assert st2["completed"] is True and st2["workspace"]


def test_setup_health_needs_auth(client):
    c, _ = client
    assert c.get("/api/setup/health").status_code == 401
