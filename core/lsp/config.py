"""Language -> language-server resolution, driven by a manifest.

Language packs are declared in ``extensions/language-servers/servers.json`` so
adding a language never touches Core code (manual v3.0 section 5, "do not
hard-code language features"). Servers are bundled under
``extensions/language-servers/node_modules`` (run with the bundled ``node`` so
this works on Windows, where the ``.bin/*.cmd`` shims are not valid Win32
executables); packs may instead name a ``command`` resolved from PATH.
"""

from __future__ import annotations

import json
import os
import shutil
from functools import lru_cache
from pathlib import Path

from core.config import REPO_ROOT

_ROOT = REPO_ROOT / "extensions" / "language-servers"
_NM = _ROOT / "node_modules"
_MANIFEST = _ROOT / "servers.json"
_NODE = shutil.which("node")

# Toolchain bin dirs that are often not on a GUI-launched process's PATH.
_EXTRA_BIN_DIRS = [
    Path.home() / ".cargo" / "bin",
    Path.home() / "go" / "bin",
    Path.home() / ".local" / "bin",
    Path("C:/Program Files/Go/bin"),
    Path("C:/Program Files/LLVM/bin"),
    Path("C:/Program Files/qemu"),
]


def _which(name: str) -> str | None:
    """PATH lookup, then well-known toolchain locations."""
    found = shutil.which(name)
    if found:
        return found
    exts = ("", ".exe", ".cmd", ".bat") if os.name == "nt" else ("",)
    for d in _EXTRA_BIN_DIRS:
        for ext in exts:
            cand = d / f"{name}{ext}"
            if cand.is_file():
                return str(cand)
    return None


@lru_cache(maxsize=1)
def _packs() -> list[dict]:
    try:
        data = json.loads(_MANIFEST.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return [p for p in data.get("packs", []) if isinstance(p, dict)]


def _pack_for(language: str) -> dict | None:
    for pack in _packs():
        if language in pack.get("languages", []):
            return pack
    return None


def _argv(pack: dict) -> list[str] | None:
    args = list(pack.get("args", []))
    if "node" in pack:
        if not _NODE:
            return None
        entry = _NM.joinpath(*pack["node"])
        if not entry.exists():
            return None
        return [_NODE, str(entry), *args]
    if "command" in pack:
        exe = _which(pack["command"])
        return [exe, *args] if exe else None
    return None


def server_for(language: str) -> list[str] | None:
    pack = _pack_for(language)
    return _argv(pack) if pack else None


def pool_for(language: str) -> str:
    """Stable key for the server process shared by a group of languages."""
    pack = _pack_for(language)
    return pack.get("pool", language) if pack else language


def lsp_language_id(language: str) -> str:
    pack = _pack_for(language)
    if pack:
        return pack.get("lspLanguageId", {}).get(language, language)
    return language


def declared_languages() -> list[str]:
    seen: list[str] = []
    for pack in _packs():
        for lang in pack.get("languages", []):
            if lang not in seen:
                seen.append(lang)
    return seen


def supported() -> dict[str, bool]:
    """{language: whether its server is actually installed and resolvable}."""
    return {lang: server_for(lang) is not None for lang in declared_languages()}
