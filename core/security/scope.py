"""Scope profiles - the authorization gate for security work.

A ScopeProfile names the engagement, the in-bounds targets and ports, the
techniques the operator is cleared for, and an authorization reference plus an
expiry. Active tools call ``permits()`` before touching anything and refuse
otherwise. Non-public targets (loopback / RFC1918) must be listed explicitly;
public targets additionally require a non-empty authorization reference.
"""

from __future__ import annotations

import fnmatch
import ipaddress
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class Technique(str, Enum):
    RECON = "recon"                    # passive: whois-style, header reads
    PORT_SCAN = "port-scan"            # TCP connect scan of listed targets
    VULN_SCAN = "vuln-scan"            # version / CVE correlation
    WEB_AUDIT = "web-audit"            # security headers, TLS, cookie flags
    CONFIG_AUDIT = "config-audit"      # local file / infra config review
    DEPENDENCY_AUDIT = "dependency-audit"
    SECRET_SCAN = "secret-scan"
    LOG_ANALYSIS = "log-analysis"


# Never permitted by any scope - not offered as tools, and refused if named.
FORBIDDEN = (
    "exploit", "exploitation", "rce", "dos", "ddos", "stress", "flood",
    "bruteforce", "brute-force", "credential-stuffing", "password-spray",
    "phishing", "social-engineering", "persistence", "backdoor", "implant",
    "lateral-movement", "privilege-escalation", "data-exfiltration", "exfil",
    "ransomware", "wiper", "evasion", "anti-forensics", "log-tampering",
)


@dataclass
class ScopeProfile:
    name: str
    authorized_targets: list[str] = field(default_factory=list)  # host / ip / CIDR / domain glob
    authorized_ports: list[int] = field(default_factory=list)  # empty = any port on a listed target
    techniques: list[str] = field(default_factory=list)        # Technique values
    authorization_ref: str = ""                                # ticket / engagement id / signed statement
    expires_at: float = 0.0                                    # unix ts; 0 = unset (required for public)
    notes: str = ""

    # -- checks ------------------------------------------------------------
    def is_expired(self, now: float | None = None) -> bool:
        now = now or time.time()
        return self.expires_at != 0.0 and now > self.expires_at

    def has_technique(self, technique: str) -> bool:
        return technique in self.techniques

    def _target_matches(self, target: str) -> bool:
        target = target.strip().lower()
        host = target.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
        for entry in self.authorized_targets:
            entry = entry.strip().lower()
            if "/" in entry and _is_cidr(entry):
                if _ip_in_cidr(host, entry):
                    return True
            elif fnmatch.fnmatch(host, entry):
                return True
        return False

    def permits(
        self, target: str, technique: str, port: int | None = None, now: float | None = None
    ) -> tuple[bool, str]:
        tech = technique.lower()
        if tech in FORBIDDEN or any(f in tech for f in FORBIDDEN):
            return False, f"technique '{technique}' is never authorized"
        if self.is_expired(now):
            return False, f"scope '{self.name}' expired"
        if not self.has_technique(tech):
            return False, f"scope '{self.name}' does not authorize '{technique}'"
        if not self._target_matches(target):
            return False, f"'{target}' is not in scope '{self.name}'"
        if _is_public_host(target) and not self.authorization_ref.strip():
            return False, "public target requires an authorization_ref on the scope"
        if _is_public_host(target) and self.expires_at == 0.0:
            return False, "public target requires an explicit expiry on the scope"
        if port is not None and self.authorized_ports and port not in self.authorized_ports:
            return False, f"port {port} not in scope '{self.name}'"
        return True, "authorized"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> ScopeProfile:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


def _is_cidr(entry: str) -> bool:
    try:
        ipaddress.ip_network(entry, strict=False)
        return True
    except ValueError:
        return False


def _ip_in_cidr(host: str, cidr: str) -> bool:
    try:
        return ipaddress.ip_address(host) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def _is_public_host(target: str) -> bool:
    host = target.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # a hostname/domain we can't classify -> treat as public (stricter)
    return not (ip.is_private or ip.is_loopback or ip.is_link_local)


class ScopeStore:
    """Scope profiles persisted as JSON under ``<root>/.vajra/security/``."""

    def __init__(self, root: str | Path) -> None:
        self.dir = Path(root) / ".vajra" / "security"

    def _path(self, name: str) -> Path:
        safe = "".join(c for c in name if c.isalnum() or c in "-_.")
        return self.dir / f"{safe or 'scope'}.json"

    def save(self, profile: ScopeProfile) -> Path:
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self._path(profile.name)
        path.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        return path

    def get(self, name: str) -> ScopeProfile | None:
        path = self._path(name)
        if not path.exists():
            return None
        try:
            return ScopeProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, TypeError):
            return None

    def list(self) -> list[ScopeProfile]:
        if not self.dir.is_dir():
            return []
        out = []
        for p in sorted(self.dir.glob("*.json")):
            try:
                out.append(ScopeProfile.from_dict(json.loads(p.read_text(encoding="utf-8"))))
            except (ValueError, TypeError):
                continue
        return out
