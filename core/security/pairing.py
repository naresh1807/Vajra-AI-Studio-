"""Device identity + pairing secrets (master-prompt P0/P3/P25).

On first run a cryptographically-random device secret and a stable device id
are generated and stored in ``data/device.json`` (git-ignored, 0600 where the
OS allows). The pairing token used to authenticate clients defaults to that
secret, so there is no shipped predictable credential. Per-device credentials
and one-time pairing codes are issued from here too.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field

from core.config import REPO_ROOT

_STORE = REPO_ROOT / "data" / "device.json"
_INSECURE = {"change-me-local-only", "", "changeme", "token", "secret"}


@dataclass
class PairedDevice:
    device_id: str
    name: str
    token: str
    created_at: float
    last_seen: float = 0.0
    revoked: bool = False


@dataclass
class DeviceIdentity:
    device_id: str
    device_secret: str            # the default pairing token for local clients
    created_at: float
    pin: str = ""                 # short one-time code, rotated on use
    pin_expires_at: float = 0.0
    devices: list[PairedDevice] = field(default_factory=list)

    # -- persistence --------------------------------------------------
    @classmethod
    def load_or_create(cls) -> DeviceIdentity:
        if _STORE.exists():
            try:
                d = json.loads(_STORE.read_text("utf-8"))
                return cls(
                    device_id=d["device_id"],
                    device_secret=d["device_secret"],
                    created_at=d.get("created_at", time.time()),
                    pin=d.get("pin", ""),
                    pin_expires_at=d.get("pin_expires_at", 0.0),
                    devices=[PairedDevice(**x) for x in d.get("devices", [])],
                )
            except (OSError, ValueError, KeyError, TypeError):
                pass
        ident = cls(
            device_id="vajra-" + secrets.token_hex(8),
            device_secret=secrets.token_urlsafe(32),
            created_at=time.time(),
        )
        ident.save()
        return ident

    def save(self) -> None:
        _STORE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "device_id": self.device_id,
            "device_secret": self.device_secret,
            "created_at": self.created_at,
            "pin": self.pin,
            "pin_expires_at": self.pin_expires_at,
            "devices": [d.__dict__ for d in self.devices],
        }
        _STORE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(_STORE, 0o600)

    # -- pairing ----------------------------------------------------
    def new_pin(self, ttl_seconds: int = 300) -> str:
        self.pin = f"{secrets.randbelow(1_000_000):06d}"
        self.pin_expires_at = time.time() + ttl_seconds
        self.save()
        return self.pin

    def redeem_pin(self, pin: str, device_name: str) -> PairedDevice | None:
        if not self.pin or time.time() > self.pin_expires_at:
            return None
        if not secrets.compare_digest(pin, self.pin):
            return None
        self.pin = ""
        self.pin_expires_at = 0.0
        dev = PairedDevice(
            device_id="dev-" + secrets.token_hex(6),
            name=device_name or "device",
            token=secrets.token_urlsafe(32),
            created_at=time.time(),
            last_seen=time.time(),
        )
        self.devices.append(dev)
        self.save()
        return dev

    def revoke(self, device_id: str) -> bool:
        for d in self.devices:
            if d.device_id == device_id and not d.revoked:
                d.revoked = True
                self.save()
                return True
        return False

    # -- auth -----------------------------------------------------
    def accepts(self, token: str | None) -> bool:
        if not token:
            return False
        if secrets.compare_digest(token, self.device_secret):
            return True
        for d in self.devices:
            if not d.revoked and secrets.compare_digest(token, d.token):
                d.last_seen = time.time()
                return True
        return False

    def all_tokens_are_secure(self, configured_token: str | None) -> bool:
        return (configured_token or "") not in _INSECURE


_identity: DeviceIdentity | None = None


def identity() -> DeviceIdentity:
    global _identity
    if _identity is None:
        _identity = DeviceIdentity.load_or_create()
    return _identity
