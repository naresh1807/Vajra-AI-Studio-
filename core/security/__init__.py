"""Authorized security engineering (manual v3.0 Phase 10).

Everything here is gated on an explicit, non-expired ScopeProfile that names
what is in bounds. Without a matching scope the active tools refuse. The
toolset is defensive / audit-oriented: dependency and secret audits, config
review, security-header checks, and an authorized-target TCP connect scan.
There are no exploitation, DoS, persistence, or evasion capabilities.
"""

from core.security.audit import config_audit, dependency_audit, secret_scan
from core.security.probe import http_security_headers, tcp_connect_scan
from core.security.scope import ScopeProfile, ScopeStore, Technique

__all__ = [
    "ScopeProfile",
    "ScopeStore",
    "Technique",
    "config_audit",
    "dependency_audit",
    "http_security_headers",
    "secret_scan",
    "tcp_connect_scan",
]
