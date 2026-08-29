"""LSP integration tests. Skipped if the bundled language servers aren't installed."""

from __future__ import annotations

import asyncio

import pytest

from core.lsp.config import declared_languages, pool_for, server_for
from core.lsp.manager import LspManager

pytestmark = pytest.mark.skipif(
    server_for("python") is None, reason="pyright not installed under extensions/language-servers"
)


def test_manifest_declares_multiple_languages():
    langs = declared_languages()
    assert {"python", "typescript", "javascript"} <= set(langs)
    # ts + js share one server process
    assert pool_for("typescript") == pool_for("javascript")
    assert pool_for("python") != pool_for("typescript")


@pytest.mark.skipif(server_for("cpp") is None, reason="clangd not installed")
async def test_clangd_diagnostics(tmp_path):
    src = tmp_path / "m.c"
    src.write_text("int main(){ return nope; }\n", encoding="utf-8")
    mgr = LspManager()
    try:
        client = await mgr.sync(str(tmp_path), str(src), src.read_text(), "c")
        assert client is not None
        for _ in range(30):
            await asyncio.sleep(0.4)
            if client.diagnostics(str(src)):
                break
        assert client.diagnostics(str(src)), "expected an undeclared-identifier diagnostic from clangd"
    finally:
        await mgr.shutdown_all()


@pytest.mark.skipif(server_for("go") is None, reason="gopls not installed")
async def test_gopls_starts(tmp_path):
    (tmp_path / "go.mod").write_text("module m\n\ngo 1.21\n", encoding="utf-8")
    src = tmp_path / "m.go"
    src.write_text("package main\n\nfunc main() {}\n", encoding="utf-8")
    mgr = LspManager()
    try:
        client = await mgr.sync(str(tmp_path), str(src), src.read_text(), "go")
        assert client is not None and client.alive
    finally:
        await mgr.shutdown_all()


@pytest.mark.skipif(server_for("json") is None, reason="json language server not installed")
async def test_json_diagnostics(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"a": 1,}\n', encoding="utf-8")
    mgr = LspManager()
    try:
        client = await mgr.sync(str(tmp_path), str(bad), bad.read_text(), "json")
        assert client is not None
        for _ in range(20):
            await asyncio.sleep(0.3)
            if client.diagnostics(str(bad)):
                break
        assert client.diagnostics(str(bad)), "expected a trailing-comma diagnostic"
    finally:
        await mgr.shutdown_all()


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
