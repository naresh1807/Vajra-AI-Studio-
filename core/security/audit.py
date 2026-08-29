"""Defensive audits over a local project - no network, no scope needed.

- dependency_audit: known-vulnerability check via pip-audit / npm audit if present
- secret_scan: committed credential / key material
- config_audit: risky file permissions, secrets tracked by git, obvious misconfig
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import stat
from dataclasses import dataclass, field
from pathlib import Path

_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws-secret-access-key", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+]{40})")),
    ("private-key-block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("nvidia-api-key", re.compile(r"\bnvapi-[A-Za-z0-9_\-]{16,}\b")),
    ("openai-api-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("generic-secret-assignment", re.compile(
        r"(?i)(api[_-]?key|secret|passwd|password|token)\s*[=:]\s*['\"]([^'\"\s]{12,})['\"]"
    )),
]

_SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", "target", ".vajra"}
_TEXT_MAX = 2 * 1024 * 1024


@dataclass
class Finding:
    severity: str          # high | medium | low | info
    kind: str
    location: str
    detail: str


@dataclass
class AuditReport:
    audit: str
    ok: bool
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""

    def as_dict(self) -> dict:
        return {
            "audit": self.audit, "ok": self.ok, "summary": self.summary,
            "findings": [f.__dict__ for f in self.findings],
        }


def _iter_text_files(root: Path):
    for p in root.rglob("*"):
        if p.is_dir() or any(part in _SKIP_DIRS for part in p.parts):
            continue
        try:
            if p.stat().st_size > _TEXT_MAX:
                continue
            yield p, p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue


def secret_scan(root: str) -> AuditReport:
    base = Path(root)
    findings: list[Finding] = []
    for path, text in _iter_text_files(base):
        rel = str(path.relative_to(base))
        if path.name in {".env.example", ".env.sample", "servers.json"}:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for name, pat in _SECRET_PATTERNS:
                if pat.search(line):
                    findings.append(Finding("high", f"secret:{name}", f"{rel}:{line_no}",
                                            "possible committed credential"))
                    break
    return AuditReport(
        "secret_scan", ok=not findings, findings=findings,
        summary=f"{len(findings)} possible secret(s)" if findings else "no secrets detected",
    )


def config_audit(root: str) -> AuditReport:
    base = Path(root)
    findings: list[Finding] = []
    gi = base / ".gitignore"
    ignored = gi.read_text(encoding="utf-8") if gi.exists() else ""
    for env in list(base.glob("**/.env")) + list(base.glob("**/*.pem")) + list(base.glob("**/id_rsa")):
        if any(part in _SKIP_DIRS for part in env.parts):
            continue
        rel = str(env.relative_to(base))
        tracked_hint = env.name not in ignored and ".env" not in ignored
        if tracked_hint:
            findings.append(Finding("high", "config:sensitive-file-not-ignored", rel,
                                    "sensitive file may be committed - add it to .gitignore"))
        try:
            mode = env.stat().st_mode
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                findings.append(Finding("medium", "config:permissive-mode", rel,
                                        f"group/other-readable ({oct(stat.S_IMODE(mode))})"))
        except OSError:
            pass
    df = base / "Dockerfile"
    if df.exists():
        dt = df.read_text(encoding="utf-8", errors="replace")
        if not re.search(r"(?m)^\s*USER\s+\S+", dt):
            findings.append(Finding("medium", "config:docker-root", "Dockerfile",
                                    "no USER instruction - container runs as root"))
        if re.search(r"(?i)(ADD|COPY)\s+http", dt):
            findings.append(Finding("low", "config:docker-remote-add", "Dockerfile",
                                    "ADD/COPY from a URL - prefer a verified download"))
    return AuditReport(
        "config_audit", ok=not findings, findings=findings,
        summary=f"{len(findings)} config issue(s)" if findings else "no obvious misconfig",
    )


async def _run(argv: list[str], cwd: str, timeout: float = 240.0) -> tuple[int | None, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, out.decode("utf-8", "replace")
    except (OSError, TimeoutError) as exc:
        return None, str(exc)


async def dependency_audit(root: str) -> AuditReport:
    base = Path(root)
    findings: list[Finding] = []
    ran_any = False

    if (base / "package.json").exists() and shutil.which("npm"):
        ran_any = True
        _, out = await _run(["npm", "audit", "--json"], str(base))
        try:
            data = json.loads(out)
            vulns = data.get("metadata", {}).get("vulnerabilities", {})
            for sev in ("critical", "high", "moderate", "low"):
                n = vulns.get(sev, 0)
                if n:
                    findings.append(Finding(
                        "high" if sev in ("critical", "high") else "medium",
                        "dependency:npm", "package.json", f"{n} {sev} advisory(ies)"))
        except ValueError:
            findings.append(Finding("info", "dependency:npm", "package.json", out[:300]))

    py_manifest = next((m for m in ("requirements.txt", "pyproject.toml") if (base / m).exists()), None)
    if py_manifest:
        if shutil.which("pip-audit"):
            ran_any = True
            _, out = await _run(["pip-audit", "-f", "json", "--progress-spinner", "off"], str(base))
            try:
                for dep in json.loads(out).get("dependencies", []):
                    for v in dep.get("vulns", []):
                        findings.append(Finding("high", "dependency:pip",
                                                f"{dep.get('name')}=={dep.get('version')}",
                                                f"{v.get('id')}: {v.get('description', '')[:160]}"))
            except ValueError:
                findings.append(Finding("info", "dependency:pip", py_manifest, out[:300]))
        else:
            findings.append(Finding(
                "info", "dependency:pip", py_manifest,
                "pip-audit not installed - `pip install pip-audit` for Python CVE checks"))

    if not ran_any and not findings:
        return AuditReport("dependency_audit", ok=True, summary="no supported manifest / auditor found")
    return AuditReport(
        "dependency_audit", ok=not any(f.severity in ("high", "medium") for f in findings),
        findings=findings,
        summary=f"{len(findings)} advisory line(s)" if findings else "no known-vulnerable dependencies",
    )
