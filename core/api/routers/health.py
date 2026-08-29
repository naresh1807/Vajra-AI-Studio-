"""Health, ping, root, device pairing, and the Vajra Mobile page."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from core.api.deps import AUTH, model_router, settings
from core.api.schemas import SimpleOk
from core.security.pairing import identity

router = APIRouter()


@router.get("/")
async def root() -> dict:
    return {
        "service": "vajra-core",
        "version": "0.3.0",
        "docs": "/docs",
        "health": "/api/health",
        "hint": "all /api/* routes need an X-Vajra-Token or Authorization: Bearer header",
    }


@router.get("/api/health")
@router.get("/health")  # kept for the desktop sidecar's readiness probe
async def health() -> dict:
    return {"status": "ok", "service": "vajra-core", "version": "0.3.0", "models": model_router.describe()}


@router.get("/api/ping", dependencies=AUTH)
async def ping() -> SimpleOk:
    return SimpleOk(detail="paired")


# -- device pairing (master-prompt P3 / P25) -------------------------
@router.get("/api/pairing/pin", dependencies=AUTH)
async def pairing_pin() -> dict:
    ident = identity()
    return {
        "device_id": ident.device_id,
        "pin": ident.new_pin(),
        "expires_in": 300,
        "connect": {"url": f"http://{settings.vajra_host}:{settings.vajra_port}"},
    }


@router.post("/api/pairing/redeem")
async def pairing_redeem(body: dict) -> dict:
    """Unauthenticated: a phone redeems the PIN for its own device credential."""
    dev = identity().redeem_pin(str(body.get("pin", "")), str(body.get("name", "device")))
    if not dev:
        raise HTTPException(401, "bad or expired pairing code")
    return {"device_id": dev.device_id, "token": dev.token, "name": dev.name}


@router.get("/api/pairing/devices", dependencies=AUTH)
async def pairing_devices() -> dict:
    ident = identity()
    return {
        "device_id": ident.device_id,
        "devices": [
            {"device_id": d.device_id, "name": d.name, "created_at": d.created_at,
             "last_seen": d.last_seen, "revoked": d.revoked}
            for d in ident.devices
        ],
    }


@router.post("/api/pairing/revoke", dependencies=AUTH)
async def pairing_revoke(body: dict) -> SimpleOk:
    ok = identity().revoke(str(body.get("device_id", "")))
    return SimpleOk(ok=ok, detail="revoked" if ok else "unknown device")


@router.get("/mobile", response_class=HTMLResponse)
async def mobile() -> str:
    from core.api.mobile import MOBILE_HTML

    return MOBILE_HTML
