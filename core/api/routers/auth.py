"""Password login for remote clients (phone, another machine).

A same-machine client uses the device secret straight from data/device.json and
never touches these routes. Everyone else logs in with the password the user set
on the desktop (or VAJRA_PASSWORD) and gets a revocable per-device token.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from core.api.deps import AUTH, log
from core.security.pairing import identity

router = APIRouter()

# per-IP failed-login tracking: 5 misses -> locked for 60s
_FAILS: dict[str, list[float]] = {}
_MAX_FAILS = 5
_LOCK_SECONDS = 60.0


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _locked(ip: str) -> bool:
    recent = [t for t in _FAILS.get(ip, []) if time.time() - t < _LOCK_SECONDS]
    _FAILS[ip] = recent
    return len(recent) >= _MAX_FAILS


def _record_fail(ip: str) -> None:
    _FAILS.setdefault(ip, []).append(time.time())


@router.get("/api/auth/status")
async def auth_status() -> dict:
    ident = identity()
    return {"configured": ident.password_configured(), "device_id": ident.device_id}


@router.post("/api/auth/setup")
async def auth_setup(body: dict) -> dict:
    """First-run only: set the password when none exists yet. Unauthenticated so
    the very first client can bootstrap; refuses once a password is set."""
    ident = identity()
    if ident.password_configured():
        raise HTTPException(409, "a password is already set - use /api/auth/change-password")
    try:
        ident.set_password(str(body.get("password", "")))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    log.info("login password set (first-run)")
    return {"ok": True}


@router.post("/api/auth/login")
async def auth_login(body: dict, request: Request) -> dict:
    ip = _client_ip(request)
    if _locked(ip):
        raise HTTPException(429, "too many attempts - wait a minute")
    dev = identity().login(str(body.get("password", "")), str(body.get("name", "device")))
    if not dev:
        _record_fail(ip)
        raise HTTPException(401, "wrong password")
    _FAILS.pop(ip, None)
    log.info("device %s logged in (%s)", dev.device_id, dev.name)
    return {"token": dev.token, "device_id": dev.device_id, "name": dev.name}


@router.post("/api/auth/change-password", dependencies=AUTH)
async def auth_change_password(body: dict) -> dict:
    ident = identity()
    if ident.password_hash and not ident.check_password(str(body.get("current", ""))):
        raise HTTPException(401, "current password is wrong")
    try:
        ident.set_password(str(body.get("new", "")))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True}


@router.get("/api/auth/devices", dependencies=AUTH)
async def auth_devices() -> dict:
    ident = identity()
    return {
        "device_id": ident.device_id,
        "devices": [
            {"device_id": d.device_id, "name": d.name, "created_at": d.created_at,
             "last_seen": d.last_seen, "revoked": d.revoked}
            for d in ident.devices
        ],
    }


@router.post("/api/auth/devices/revoke", dependencies=AUTH)
async def auth_revoke(body: dict) -> dict:
    ok = identity().revoke(str(body.get("device_id", "")))
    return {"ok": ok}
