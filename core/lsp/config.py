"""Language -> language-server command mapping.

Servers are bundled under extensions/language-servers/ so the IDE stays
local-first (manual v3.0 sections 5 and 28). Falls back to PATH.
"""

from __future__ import annotations

import shutil

from core.config import REPO_ROOT

_NM = REPO_ROOT / "extensions" / "language-servers" / "node_modules"
_NODE = shutil.which("node")

# Real JS entrypoints - run with `node` so this works on Windows (where the
# .bin/*.cmd shims are not valid Win32 executables for CreateProcess).
_JS_ENTRY: dict[str, tuple[str, ...]] = {
    "pyright": ("pyright", "langserver.index.js"),
    "tsls": ("typescript-language-server", "lib", "cli.mjs"),
}


def _node_server(entry_key: str, *extra: str) -> list[str] | None:
    if not _NODE:
        return None
    js = _NM.joinpath(*_JS_ENTRY[entry_key])
    if not js.exists():
        return None
    return [_NODE, str(js), *extra]


#: language id -> factory
_SERVERS = {
    "python": lambda: _node_server("pyright", "--stdio"),
    "typescript": lambda: _node_server("tsls", "--stdio"),
    "javascript": lambda: _node_server("tsls", "--stdio"),
    "typescriptreact": lambda: _node_server("tsls", "--stdio"),
    "javascriptreact": lambda: _node_server("tsls", "--stdio"),
}

_LSP_LANGUAGE_ID = {
    "python": "python",
    "typescript": "typescript",
    "javascript": "javascript",
    "typescriptreact": "typescriptreact",
    "javascriptreact": "javascriptreact",
}


def server_for(language: str) -> list[str] | None:
    factory = _SERVERS.get(language)
    return factory() if factory else None


def lsp_language_id(language: str) -> str:
    return _LSP_LANGUAGE_ID.get(language, language)


def supported() -> dict[str, bool]:
    return {lang: server_for(lang) is not None for lang in ("python", "typescript", "javascript")}
