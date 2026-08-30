"""Device identity + password login + security-hardening edge cases (P0/P3/P4/P32)."""

from __future__ import annotations

import importlib

import pytest

from core.security import pairing


@pytest.fixture
def ident(tmp_path, monkeypatch):
    monkeypatch.setattr(pairing, "_STORE", tmp_path / "device.json")
    monkeypatch.setattr(pairing, "_identity", None)
    monkeypatch.delenv("VAJRA_PASSWORD", raising=False)
    return pairing.DeviceIdentity.load_or_create()


def test_first_run_generates_a_strong_secret(ident):
    assert ident.device_id.startswith("vajra-")
    assert len(ident.device_secret) >= 40
    assert pairing._STORE.exists()
    assert ident.password_configured() is False  # no password until the user sets one


def test_default_token_is_flagged_insecure(ident):
    assert ident.all_tokens_are_secure("change-me-local-only") is False
    assert ident.all_tokens_are_secure("") is False
    assert ident.all_tokens_are_secure("a-real-long-secret-value") is True


def test_device_secret_authenticates(ident):
    assert ident.accepts(ident.device_secret) is True
    assert ident.accepts("nope") is False
    assert ident.accepts(None) is False


def test_password_set_check_and_login(ident):
    with pytest.raises(ValueError):
        ident.set_password("short")
    ident.set_password("correct horse battery")
    assert ident.password_configured() is True
    assert ident.check_password("correct horse battery") is True
    assert ident.check_password("wrong") is False
    # a login mints a usable, revocable token
    assert ident.login("wrong", "Pixel") is None
    dev = ident.login("correct horse battery", "Pixel")
    assert dev and ident.accepts(dev.token) is True
    assert ident.revoke(dev.device_id) is True
    assert ident.accepts(dev.token) is False


def test_hash_is_scrypt_and_not_the_plaintext(ident):
    ident.set_password("hunter2 hunter2")
    assert ident.password_hash.startswith("scrypt$")
    assert "hunter2" not in ident.password_hash


def test_env_password_overrides_stored_hash(ident, monkeypatch):
    ident.set_password("stored-password")
    monkeypatch.setenv("VAJRA_PASSWORD", "env-password")
    assert ident.check_password("env-password") is True
    assert ident.check_password("stored-password") is False
    assert ident.password_configured() is True


def test_persistence_round_trip(ident):
    ident.set_password("persist me please")
    dev = ident.login("persist me please", "d1")
    reloaded = pairing.DeviceIdentity.load_or_create()
    assert reloaded.device_secret == ident.device_secret
    assert reloaded.password_hash == ident.password_hash
    assert reloaded.accepts(dev.token) is True


# -- API-level checks -------------------------------------------------
@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("VAJRA_DB_PATH", f"./data/pair-test-{tmp_path.name}.db")
    monkeypatch.setenv("VAJRA_PAIRING_TOKEN", "test-token")
    monkeypatch.delenv("VAJRA_PASSWORD", raising=False)
    monkeypatch.setattr(pairing, "_STORE", tmp_path / "device.json")
    monkeypatch.setattr(pairing, "_identity", None)
    import core.api.main as main

    importlib.reload(main)

    class _Stub:
        def describe(self):
            return {"primary": "stub", "fallback": "stub"}

    main.router = _Stub()
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def test_api_v1_alias(client):
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/ping").status_code == 401  # still needs auth


def test_default_token_rejected(client):
    assert client.get("/api/ping", headers={"X-Vajra-Token": "change-me-local-only"}).status_code == 401
    assert client.get("/api/ping", headers={"X-Vajra-Token": "test-token"}).status_code == 200


def test_password_login_flow_over_http(client):
    # not configured yet
    assert client.get("/api/auth/status").json()["configured"] is False
    # first-run setup is unauthenticated, once
    assert client.post("/api/auth/setup", json={"password": "phone-pass-123"}).status_code == 200
    assert client.post("/api/auth/setup", json={"password": "again"}).status_code == 409
    assert client.get("/api/auth/status").json()["configured"] is True

    assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    ok = client.post("/api/auth/login", json={"password": "phone-pass-123", "name": "Phone"})
    assert ok.status_code == 200
    tok = ok.json()["token"]
    assert client.get("/api/ping", headers={"X-Vajra-Token": tok}).status_code == 200

    h = {"X-Vajra-Token": "test-token"}
    devs = client.get("/api/auth/devices", headers=h).json()["devices"]
    phone = next(d for d in devs if d["name"] == "Phone")
    client.post("/api/auth/devices/revoke", json={"device_id": phone["device_id"]}, headers=h)
    assert client.get("/api/ping", headers={"X-Vajra-Token": tok}).status_code == 401


def test_login_lockout_after_repeated_failures(client):
    client.post("/api/auth/setup", json={"password": "the-real-password"})
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "x"}).status_code == 401
    # now locked, even a correct password is deferred
    assert client.post("/api/auth/login", json={"password": "the-real-password"}).status_code == 429


def test_cors_not_wildcard(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") not in ("*", "https://evil.example")


def test_lan_bind_gate(ident):
    def would_refuse(configured: str) -> bool:
        configured = (configured or "").strip()
        return bool(configured) and not ident.all_tokens_are_secure(configured)

    assert would_refuse("") is False
    assert would_refuse("change-me-local-only") is True
    assert would_refuse("changeme") is True
    assert would_refuse("a-strong-random-secret-value-here") is False
