"""Active checks against an authorized target. Every function takes a
ScopeProfile and refuses anything it does not permit. These are connect-only:
a TCP connect scan and an HTTP(S) security-header / TLS read. No payloads, no
auth attempts, no fuzzing.
"""

from __future__ import annotations

import asyncio
import contextlib
import ssl
from dataclasses import dataclass, field

from core.security.scope import ScopeProfile, Technique

# Security-relevant response headers we report on (present / absent).
_WANT_HEADERS = (
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
)
_LEAKY_HEADERS = ("server", "x-powered-by", "x-aspnet-version", "x-runtime")

_DEFAULT_PORTS = (22, 80, 443, 3306, 5432, 6379, 8080, 8443)


@dataclass
class ScanResult:
    authorized: bool
    reason: str = ""
    target: str = ""
    open_ports: list[int] = field(default_factory=list)
    closed_ports: list[int] = field(default_factory=list)
    details: dict = field(default_factory=dict)


async def _probe_port(host: str, port: int, timeout: float) -> bool:
    try:
        fut = asyncio.open_connection(host, port)
        _reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        with contextlib.suppress(OSError, TimeoutError):
            await writer.wait_closed()
        return True
    except (OSError, TimeoutError):
        return False


async def tcp_connect_scan(
    scope: ScopeProfile, target: str, ports: list[int] | None = None, timeout: float = 2.0
) -> ScanResult:
    host = target.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    ports = ports or list(_DEFAULT_PORTS)
    # authorize each port individually
    for p in ports:
        ok, reason = scope.permits(target, Technique.PORT_SCAN.value, port=p)
        if not ok:
            return ScanResult(authorized=False, reason=reason, target=host)

    sem = asyncio.Semaphore(64)

    async def one(p: int) -> tuple[int, bool]:
        async with sem:
            return p, await _probe_port(host, p, timeout)

    results = await asyncio.gather(*(one(p) for p in ports))
    opened = sorted(p for p, up in results if up)
    closed = sorted(p for p, up in results if not up)
    return ScanResult(
        authorized=True, target=host, open_ports=opened, closed_ports=closed,
        reason="authorized",
    )


async def http_security_headers(scope: ScopeProfile, url: str, timeout: float = 6.0) -> ScanResult:
    if "://" not in url:
        url = "https://" + url
    ok, reason = scope.permits(url, Technique.WEB_AUDIT.value)
    if not ok:
        return ScanResult(authorized=False, reason=reason, target=url)

    try:
        import httpx
    except ImportError:  # httpx is a Core dependency, but stay defensive
        return ScanResult(authorized=True, target=url, reason="httpx unavailable")

    details: dict = {}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, verify=True) as client:
            resp = await client.get(url)
        headers = {k.lower(): v for k, v in resp.headers.items()}
        details["status"] = resp.status_code
        details["missing_security_headers"] = [h for h in _WANT_HEADERS if h not in headers]
        details["present_security_headers"] = [h for h in _WANT_HEADERS if h in headers]
        details["version_disclosure"] = {h: headers[h] for h in _LEAKY_HEADERS if h in headers}
        if url.startswith("https://"):
            details["tls"] = await _tls_summary(url, timeout)
    except (httpx.HTTPError, ssl.SSLError) as exc:
        details["error"] = f"{type(exc).__name__}: {exc}"
    return ScanResult(authorized=True, target=url, reason="authorized", details=details)


async def _tls_summary(url: str, timeout: float) -> dict:
    host = url.split("://", 1)[1].split("/", 1)[0]
    port = 443
    if ":" in host:
        host, p = host.rsplit(":", 1)
        port = int(p)
    ctx = ssl.create_default_context()
    try:
        fut = asyncio.open_connection(host, port, ssl=ctx, server_hostname=host)
        _reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        ssl_obj = writer.get_extra_info("ssl_object")
        cert = ssl_obj.getpeercert() if ssl_obj else {}
        writer.close()
        return {
            "protocol": ssl_obj.version() if ssl_obj else None,
            "cipher": (ssl_obj.cipher() or [None])[0] if ssl_obj else None,
            "not_after": cert.get("notAfter"),
            "subject": dict(x[0] for x in cert.get("subject", [])),
        }
    except (OSError, ssl.SSLError, TimeoutError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
