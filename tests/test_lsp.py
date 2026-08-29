"""LSP integration tests. Skipped if the bundled language servers aren't installed."""

from __future__ import annotations

import asyncio

import pytest

from core.lsp.config import server_for
from core.lsp.manager import LspManager

pytestmark = pytest.mark.skipif(
    server_for("python") is None, reason="pyright not installed under extensions/language-servers"
)


async def test_python_diagnostics(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("def f(:\n    return 1\n", encoding="utf-8")
    mgr = LspManager()
    try:
        client = await mgr.sync(str(tmp_path), str(bad), bad.read_text(), "python")
        assert client is not None
        for _ in range(20):
            await asyncio.sleep(0.4)
            if client.diagnostics(str(bad)):
                break
        diags = client.diagnostics(str(bad))
        assert diags, "expected a syntax diagnostic from pyright"
        assert any("message" in d for d in diags)
    finally:
        await mgr.shutdown_all()


async def test_python_hover_and_completion(tmp_path):
    src = tmp_path / "m.py"
    src.write_text("import os\nos.\n", encoding="utf-8")
    mgr = LspManager()
    try:
        client = await mgr.sync(str(tmp_path), str(src), src.read_text(), "python")
        assert client is not None
        await asyncio.sleep(1.5)
        items = await client.completion(str(src), line=1, character=3)
        labels = {i.get("label") for i in items}
        assert "getcwd" in labels or "path" in labels
    finally:
        await mgr.shutdown_all()
