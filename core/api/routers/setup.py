"""First-run wizard + environment health (master-prompt P35 / P36).

GET  /api/setup/health   environment diagnostics (never fails on optional tools)
GET  /api/setup/state    has first-run been completed? + saved choices
POST /api/setup/complete {workspace?, model?} -> marks first-run done
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter

from core.api.deps import AUTH, settings
from core.config import REPO_ROOT
from core.runtime.doctor import run_doctor
from core.security.pairing import identity

router = APIRouter()

_STATE = REPO_ROOT / "data" / "setup.json"


def _load() -> dict:
    try:
        return json.loads(_STATE.read_text("utf-8"))
    except (OSError, ValueError):
        return {"completed": False}


def _save(state: dict) -> None:
    _STATE.parent.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


@router.get("/api/setup/health", dependencies=AUTH)
async def setup_health() -> dict:
    return await run_doctor()


@router.get("/api/setup/state", dependencies=AUTH)
async def setup_state() -> dict:
    st = _load()
    ident = identity()
    return {
        "completed": st.get("completed", False),
        "workspace": st.get("workspace"),
        "device_id": ident.device_id,
        "paired_devices": len([d for d in ident.devices if not d.revoked]),
        "model": {
            "primary": f"{settings.nvidia_base_url and 'nvidia_nim'}:{settings.vajra_nemotron_model}",
            "has_key": bool(settings.nvidia_api_key),
            "local_base_url": settings.vajra_local_base_url,
        },
    }


@router.post("/api/setup/complete", dependencies=AUTH)
async def setup_complete(body: dict) -> dict:
    st = _load()
    st["completed"] = True
    st["completed_at"] = time.time()
    if body.get("workspace"):
        p = Path(str(body["workspace"])).expanduser()
        st["workspace"] = str(p)
    if body.get("model"):
        st["model"] = body["model"]
    _save(st)
    return {"ok": True, "state": st}
