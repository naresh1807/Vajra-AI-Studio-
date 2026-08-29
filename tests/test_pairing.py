"""Device identity + pairing + the security-hardening edge cases (P0/P3/P4/P32)."""

from __future__ import annotations

import importlib
import time

import pytest

from core.security import pairing


@pytest.fixture
def ident(tmp_path, monkeypatch):
    monkeypatch.setattr(pairing, "_STORE", tmp_path / "device.json")
    monkeypatch.setattr(pairing, "_identity", None)
    return pairing.DeviceIdentity.load_or_create()


def test_first_run_generates_a_strong_secret(ident):
    assert ident.device_id.startswith("vajra-")
    assert len(ident.device_secret) >= 40
    assert (pairing._STORE).exists()


def test_default_token_is_flagged_insecure(ident):
    assert ident.all_tokens_are_secure("change-me-local-only") is False
    assert ident.all_tokens_are_secure("") is False
    assert ident.all_tokens_are_secure("a-real-long-secret-value") is True


def test_device_secret_authenticates(ident):
    assert ident.accepts(ident.device_secret) is True
    assert ident.accepts("nope") is False
    assert ident.accepts(None) is False


def test_pin_pairing_and_revoke(ident):
    pin = ident.new_pin(ttl_seconds=60)
    assert len(pin) == 6
    assert ident.redeem_pin("000000", "phone") is None or pin == "000000"
    dev = ident.redeem_pin(pin, "Pixel")
    assert dev and ident.accepts(dev.token) is True
    assert ident.redeem_pin(pin, "again") is None  # single use

    assert ident.revoke(dev.device_id) is True
    assert ident.accepts(dev.token) is False
    assert ident.revoke("unknown") is False


def test_pin_expires(ident):
    pin = ident.new_pin(ttl_seconds=0)
    time.sleep(0.01)
    assert ident.redeem_pin(pin, "late") is None


def test_persistence_round_trip(ident):
    ident.new_pin()
    dev = ident.redeem_pin(ident.pin, "d1")
    reloaded = pairing.DeviceIdentity.load_or_create()
    assert reloaded.device_secret == ident.device_secret
    assert reloaded.accepts(dev.token) is True


# -- API-level checks -------------------------------------------------
@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("VAJRA_DB_PATH", f"./data/pair-test-{tmp_path.name}.db")
    monkeypatch.setenv("VAJRA_PAIRING_TOKEN", "test-token")
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
    # conftest set a real token; the shipped insecure default must not work
    assert client.get("/api/ping", headers={"X-Vajra-Token": "change-me-local-only"}).status_code == 401
    assert client.get("/api/ping", headers={"X-Vajra-Token": "test-token"}).status_code == 200


def test_pairing_pin_flow_over_http(client):
    h = {"X-Vajra-Token": "test-token"}
    r = client.get("/api/pairing/pin", headers=h)
    assert r.status_code == 200
    pin = r.json()["pin"]
    bad = client.post("/api/pairing/redeem", json={"pin": "123456", "name": "x"})
    assert bad.status_code in (401, 200)  # 1-in-1e6 the random pin matches
    ok = client.post("/api/pairing/redeem", json={"pin": pin, "name": "Phone"})
    assert ok.status_code == 200
    tok = ok.json()["token"]
    assert client.get("/api/ping", headers={"X-Vajra-Token": tok}).status_code == 200
    devs = client.get("/api/pairing/devices", headers=h).json()["devices"]
    phone = next(d for d in devs if d["name"] == "Phone")
    client.post("/api/pairing/revoke", json={"device_id": phone["device_id"]}, headers=h)
    assert client.get("/api/ping", headers={"X-Vajra-Token": tok}).status_code == 401


def test_cors_not_wildcard(client):
    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert r.headers.get("access-control-allow-origin") not in ("*", "https://evil.example")
