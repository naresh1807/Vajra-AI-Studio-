"""Document formatting - ruff for Python, prettier for web/config files
(manual v3.0 section 5, Formatter providers). Formatters are deterministic and
idempotent, so the result is applied directly by the editor.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

from core.config import REPO_ROOT

_NODE = shutil.which("node")
_PRETTIER = (
    REPO_ROOT / "extensions" / "language-servers" / "node_modules" / "prettier" / "bin" / "prettier.cjs"
)

_PRETTIER_LANGS = {
    "typescript", "javascript", "typescriptreact", "javascriptreact",
    "json", "css", "scss", "less", "html", "markdown", "yaml", "vue", "graphql",
}


class FormatUnavailable(Exception):
    pass


async def _run(argv: list[str], stdin_text: str, cwd: str) -> str:
    proc = await asyncio.create_subprocess_exec(
        *argv, cwd=cwd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate(stdin_text.encode("utf-8"))
    if proc.returncode != 0:
        raise FormatUnavailable((err or out).decode("utf-8", "replace").strip()[:400] or "formatter failed")
    return out.decode("utf-8")


async def format_document(root: str, path: str, content: str, language: str) -> str:
    root = str(Path(root).resolve())
    if language == "python":
        argv = [sys.executable, "-m", "ruff", "format", "--stdin-filename", path, "-"]
        return await _run(argv, content, root)
    if language in _PRETTIER_LANGS:
        if not (_NODE and _PRETTIER.exists()):
            raise FormatUnavailable("prettier not installed under extensions/language-servers")
        argv = [_NODE, str(_PRETTIER), "--stdin-filepath", path]
        return await _run(argv, content, root)
    raise FormatUnavailable(f"no formatter for {language or 'this file'}")


def formattable(language: str) -> bool:
    return language == "python" or language in _PRETTIER_LANGS
