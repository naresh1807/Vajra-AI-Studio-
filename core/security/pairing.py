"""Device identity + password login (master-prompt P0/P3/P25).

On first run a cryptographically-random ``device_secret`` and a stable
``device_id`` are generated in ``data/device.json`` (git-ignored, 0600 where the
OS allows). The device secret is the zero-config credential for a same-machine
client (the VS Code extension reads it directly).

Other clients - a phone, another machine - log in with a **password** the user
sets on the desktop (or via ``VAJRA_PASSWORD``). A successful login mints a
per-device token that is stored here and can be revoked.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass, field

from core.config import REPO_ROOT

_STORE = REPO_ROOT / "data" / "device.json"
_INSECURE = {"change-me-local-only", "", "changeme", "token", "secret", "password"}

# scrypt work factors - fine for an interactive login on a laptop.
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
_MIN_PASSWORD_LEN = 6


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=32, **_SCRYPT)
    return f"scrypt${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(dk_b64)
    except (ValueError, TypeError):
        return False
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=len(expected), **_SCRYPT)
    return secrets.compare_digest(dk, expected)


def _env_password() -> str:
    return (os.environ.get("VAJRA_PASSWORD") or "").strip()


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
    device_secret: str            # zero-config credential for a same-machine client
    created_at: float
    password_hash: str = ""       # scrypt$... - set by the user; env var overrides
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
                    password_hash=d.get("password_hash", ""),
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
            "password_hash": self.password_hash,
            "devices": [d.__dict__ for d in self.devices],
        }
        _STORE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        with contextlib.suppress(OSError):
            os.chmod(_STORE, 0o600)

    # -- password -------------------------------------------------
    def password_configured(self) -> bool:
        return bool(self.password_hash) or bool(_env_password())

    def set_password(self, password: str) -> None:
        password = (password or "").strip()
        if len(password) < _MIN_PASSWORD_LEN:
            raise ValueError(f"password must be at least {_MIN_PASSWORD_LEN} characters")
        self.password_hash = hash_password(password)
        self.save()

    def check_password(self, password: str) -> bool:
        password = (password or "").strip()
        if not password:
            return False
        env = _env_password()
        if env:
            return secrets.compare_digest(password, env)
        return bool(self.password_hash) and verify_password(password, self.password_hash)

    def login(self, password: str, device_name: str) -> PairedDevice | None:
        """Verify the password and mint a per-device token."""
        if not self.check_password(password):
            return None
        dev = PairedDevice(
            device_id="dev-" + secrets.token_hex(6),
            name=(device_name or "device")[:60],
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
