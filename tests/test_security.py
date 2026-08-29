"""Authorized-security engineering: scope gate, audits, scoped probes, registry."""

from __future__ import annotations

import socket
import time

from core.security.audit import config_audit, dependency_audit, secret_scan
from core.security.probe import tcp_connect_scan
from core.security.scope import ScopeProfile, ScopeStore, Technique
from core.tools import ToolCall, ToolContext, build_security_registry

FUTURE = time.time() + 3600


def _scope(**kw) -> ScopeProfile:
    base = dict(
        name="engagement-1",
        authorized_targets=["127.0.0.1", "10.0.0.0/24", "*.lab.example"],
        techniques=[Technique.PORT_SCAN.value, Technique.WEB_AUDIT.value],
        authorization_ref="TICKET-42",
        expires_at=FUTURE,
    )
    base.update(kw)
    return ScopeProfile(**base)


# -- scope gate ---------------------------------------------------------
def test_forbidden_technique_never_permitted():
    ok, why = _scope(techniques=["exploit"]).permits("127.0.0.1", "exploit")
    assert not ok and "never authorized" in why


def test_expired_scope_refused():
    ok, _ = _scope(expires_at=time.time() - 10).permits("127.0.0.1", "port-scan")
    assert not ok


def test_technique_not_in_scope():
    ok, why = _scope(techniques=["web-audit"]).permits("127.0.0.1", "port-scan")
    assert not ok and "does not authorize" in why


def test_target_must_be_listed():
    ok, why = _scope().permits("8.8.8.8", "port-scan")
    assert not ok and "not in scope" in why


def test_private_target_listed_is_ok():
    ok, _ = _scope().permits("10.0.0.15", "port-scan", port=None)
    assert ok


def test_glob_and_cidr_matching():
    s = _scope()
    assert s.permits("host.lab.example", "web-audit")[0]
    assert s.permits("10.0.0.200", "port-scan")[0]


def test_public_target_requires_ref_and_expiry():
    s = _scope(authorized_targets=["scanme.example"], authorization_ref="", expires_at=FUTURE)
    ok, why = s.permits("scanme.example", "web-audit")
    assert not ok and "authorization_ref" in why
    s2 = _scope(authorized_targets=["scanme.example"], authorization_ref="R", expires_at=0.0)
    assert not s2.permits("scanme.example", "web-audit")[0]
    s3 = _scope(authorized_targets=["scanme.example"], authorization_ref="R", expires_at=FUTURE)
    assert s3.permits("scanme.example", "web-audit")[0]


def test_port_restriction():
    s = _scope(authorized_ports=[80, 443])
    assert not s.permits("127.0.0.1", "port-scan", port=22)[0]
    assert s.permits("127.0.0.1", "port-scan", port=443)[0]


def test_scope_store_roundtrip(tmp_path):
    store = ScopeStore(tmp_path)
    store.save(_scope(name="eng-x"))
    got = store.get("eng-x")
    assert got and got.authorization_ref == "TICKET-42"
    assert [s.name for s in store.list()] == ["eng-x"]


# -- defensive audits -------------------------------------------------
def test_secret_scan_flags_keys_and_skips_examples(tmp_path):
    (tmp_path / "app.py").write_text('KEY = "AKIA1234567890ABCD90"\n', encoding="utf-8")
    (tmp_path / ".env.example").write_text('AWS_SECRET_ACCESS_KEY=' + "x" * 40 + "\n", encoding="utf-8")
    (tmp_path / "id_ed25519").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\n", encoding="utf-8")
    rep = secret_scan(str(tmp_path))
    locs = {f.location.split(":")[0] for f in rep.findings}
    assert "app.py" in locs and "id_ed25519" in locs
    assert not any("env.example" in ln for ln in locs)
    assert not rep.ok


def test_config_audit_flags_docker_root_and_unignored_env(tmp_path):
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\nCOPY . /app\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    rep = config_audit(str(tmp_path))
    kinds = {f.kind for f in rep.findings}
    assert "config:docker-root" in kinds
    assert any("not-ignored" in k for k in kinds)


async def test_dependency_audit_no_manifest(tmp_path):
    rep = await dependency_audit(str(tmp_path))
    assert rep.audit == "dependency_audit" and isinstance(rep.findings, list)


def test_secret_scan_ignores_placeholders_and_downgrades_test_files(tmp_path):
    (tmp_path / "config.ts").write_text('pairingToken: "change-me-local-only"\n', encoding="utf-8")
    tdir = tmp_path / "tests"
    tdir.mkdir()
    (tdir / "test_x.py").write_text('KEY = "AKIA1234567890ABCD90"\n', encoding="utf-8")
    rep = secret_scan(str(tmp_path))
    assert not any("config.ts" in f.location for f in rep.findings)  # placeholder skipped
    test_hits = [f for f in rep.findings if "test_x.py" in f.location]
    assert test_hits and all(f.severity == "low" for f in test_hits)
    assert rep.ok  # no high-severity findings


async def test_audit_tool_reports_success_with_findings(tmp_path):
    (tmp_path / "leak.py").write_text('T = "ghp_' + "a" * 36 + '"\n', encoding="utf-8")
    reg = build_security_registry()
    res = await reg.execute(
        ToolCall(tool_name="secret_scan", arguments={}),
        ToolContext(workspace_root=str(tmp_path)),
    )
    assert res.success is True                 # the audit ran
    assert res.metadata["clean"] is False      # ...and found something
    assert res.metadata["findings"] >= 1


# -- scoped active probe --------------------------------------------
async def test_tcp_scan_refuses_unauthorized():
    res = await tcp_connect_scan(_scope(), "192.168.99.99")
    assert not res.authorized and "not in scope" in res.reason


async def test_tcp_scan_authorized_localhost():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        s = _scope(authorized_ports=[port])
        res = await tcp_connect_scan(s, "127.0.0.1", ports=[port])
        assert res.authorized and port in res.open_ports
    finally:
        srv.close()


# -- registry ---------------------------------------------------------
def test_security_registry_wiring():
    reg = build_security_registry()
    names = set(reg.names())
    assert {"dependency_audit", "secret_scan", "config_audit", "port_scan", "http_audit"} <= names
    ctx = ToolContext(workspace_root="")
    assert not reg.check(ToolCall(tool_name="secret_scan", arguments={}), ctx).requires_approval
    assert reg.check(ToolCall(tool_name="port_scan", arguments={}), ctx).requires_approval
    assert reg.check(ToolCall(tool_name="http_audit", arguments={}), ctx).requires_approval


async def test_port_scan_tool_refuses_without_scope(tmp_path):
    reg = build_security_registry()
    res = await reg.execute(
        ToolCall(tool_name="port_scan", arguments={"scope": "nope", "target": "127.0.0.1"}),
        ToolContext(workspace_root=str(tmp_path)),
        approved=True,
    )
    assert not res.success and "no scope profile" in res.stderr
