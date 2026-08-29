"""Authorized-security tools (manual v3.0 Phase 10).

Defensive audits (dependency / secret / config) run against the open project
with no network and no scope. Active checks (port_scan, http_audit) require a
named, non-expired ScopeProfile that lists the target, and are approval-gated.
No exploitation / DoS / evasion tooling exists here by design.
"""

from __future__ import annotations

import json
from typing import Any

from core.policy.engine import RiskLevel
from core.security import audit as auditsvc
from core.security import probe as probesvc
from core.security.scope import ScopeStore
from core.tools.base import Tool, ToolContext, ToolResult


def _audit_result(report) -> ToolResult:
    """An audit that ran is a successful tool call - findings are data, not a
    failure. `clean` in metadata carries the pass/fail signal for the agent."""
    body = json.dumps(report.as_dict(), indent=2)[:40000]
    return ToolResult(
        success=True, stdout=body,
        metadata={"audit": report.audit, "clean": report.ok, "findings": len(report.findings)},
    )


class SecurityScopesTool(Tool):
    name = "security_scopes"
    description = "List the authorized-security scope profiles defined for this project (name, targets, techniques, expiry)."
    risk = RiskLevel.LOW

    async def run(self, ctx: ToolContext, **_: Any) -> ToolResult:
        scopes = ScopeStore(ctx.workspace_root or ".").list()
        if not scopes:
            return ToolResult.ok(
                "no scope profiles. Active checks are unavailable until one is defined "
                "(POST /api/security/scopes or .vajra/security/<name>.json)."
            )
        rows = [
            f"- {s.name}: targets={s.authorized_targets} techniques={s.techniques} "
            f"ref={'set' if s.authorization_ref else 'none'} "
            f"{'EXPIRED' if s.is_expired() else 'valid'}"
            for s in scopes
        ]
        return ToolResult.ok("\n".join(rows), metadata={"count": len(scopes)})


class DependencyAuditTool(Tool):
    name = "dependency_audit"
    description = "Check the project's declared dependencies for known vulnerabilities (pip-audit / npm audit if installed)."
    risk = RiskLevel.LOW
    timeout_seconds = 300

    async def run(self, ctx: ToolContext, **_: Any) -> ToolResult:
        report = await auditsvc.dependency_audit(ctx.workspace_root or ".")
        return _audit_result(report)


class SecretScanTool(Tool):
    name = "secret_scan"
    description = "Scan the project tree for committed credentials, API keys and private-key material."
    risk = RiskLevel.LOW
    timeout_seconds = 120

    async def run(self, ctx: ToolContext, **_: Any) -> ToolResult:
        return _audit_result(auditsvc.secret_scan(ctx.workspace_root or "."))


class ConfigAuditTool(Tool):
    name = "config_audit"
    description = "Review project config for risky settings: sensitive files not git-ignored, permissive permissions, root Docker containers."
    risk = RiskLevel.LOW
    timeout_seconds = 60

    async def run(self, ctx: ToolContext, **_: Any) -> ToolResult:
        return _audit_result(auditsvc.config_audit(ctx.workspace_root or "."))


def _resolve_scope(ctx: ToolContext, scope: str):
    return ScopeStore(ctx.workspace_root or ".").get(scope)


class PortScanTool(Tool):
    name = "port_scan"
    description = (
        "TCP connect scan (open/closed only, no payloads) of a target that is listed in a "
        "named scope profile. Requires approval."
    )
    risk = RiskLevel.ELEVATED
    timeout_seconds = 180
    parameters = {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "description": "name of an authorized scope profile"},
            "target": {"type": "string", "description": "host or IP in that scope"},
            "ports": {"type": "array", "items": {"type": "integer"}},
        },
        "required": ["scope", "target"],
    }

    async def run(
        self, ctx: ToolContext, scope: str = "", target: str = "", ports: list[int] | None = None, **_: Any
    ) -> ToolResult:
        profile = _resolve_scope(ctx, scope)
        if not profile:
            return ToolResult.fail(f"no scope profile named '{scope}'")
        res = await probesvc.tcp_connect_scan(profile, target, ports)
        if not res.authorized:
            return ToolResult.fail(f"refused: {res.reason}")
        return ToolResult.ok(
            f"{res.target}: open={res.open_ports or 'none'}  closed={len(res.closed_ports)} port(s)",
            metadata={"open_ports": res.open_ports, "scope": scope},
        )


class HttpAuditTool(Tool):
    name = "http_audit"
    description = (
        "Fetch one HTTP(S) URL (in a named scope) and report security headers, version disclosure "
        "and a TLS summary. GET only, no redirects, no auth. Requires approval."
    )
    risk = RiskLevel.ELEVATED
    timeout_seconds = 60
    parameters = {
        "type": "object",
        "properties": {
            "scope": {"type": "string"},
            "url": {"type": "string"},
        },
        "required": ["scope", "url"],
    }

    async def run(self, ctx: ToolContext, scope: str = "", url: str = "", **_: Any) -> ToolResult:
        profile = _resolve_scope(ctx, scope)
        if not profile:
            return ToolResult.fail(f"no scope profile named '{scope}'")
        res = await probesvc.http_security_headers(profile, url)
        if not res.authorized:
            return ToolResult.fail(f"refused: {res.reason}")
        return ToolResult.ok(json.dumps(res.details, indent=2)[:20000], metadata={"scope": scope})
