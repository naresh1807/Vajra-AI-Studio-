"""Test-explorer backend: framework detection, discovery, run parsing."""

from __future__ import annotations

import sys
import textwrap

from core.runtime.testing import detect_framework, discover, run_tests


def test_detect_framework(tmp_path):
    assert detect_framework(str(tmp_path)) == "unknown"
    (tmp_path / "test_x.py").write_text("def test_ok(): assert 1\n", encoding="utf-8")
    assert detect_framework(str(tmp_path)) == "pytest"

    node = tmp_path / "node"
    node.mkdir()
    (node / "package.json").write_text('{"scripts": {"test": "vitest run"}}', encoding="utf-8")
    assert detect_framework(str(node)) == "node"


async def test_discover_and_run_pytest(tmp_path):
    (tmp_path / "test_sample.py").write_text(
        textwrap.dedent(
            """
            def test_pass():
                assert 2 + 2 == 4

            def test_fail():
                assert 2 + 2 == 5
            """
        ),
        encoding="utf-8",
    )
    d = await discover(str(tmp_path))
    assert d["framework"] == "pytest"
    assert any(t.endswith("::test_pass") for t in d["tests"])

    run = await run_tests(str(tmp_path))
    assert run.framework == "pytest" and run.ok is False
    outcomes = {c.id.split("::")[-1]: c.outcome for c in run.cases}
    assert outcomes.get("test_pass") == "passed"
    assert outcomes.get("test_fail") == "failed"
    assert run.totals.get("passed") == 1 and run.totals.get("failed") == 1


async def test_run_single_node_id(tmp_path):
    (tmp_path / "test_one.py").write_text(
        "def test_a(): assert True\ndef test_b(): assert False\n", encoding="utf-8"
    )
    run = await run_tests(str(tmp_path), [f"{tmp_path / 'test_one.py'}::test_a"])
    assert run.ok is True
    assert [c.outcome for c in run.cases] == ["passed"]


async def test_discover_non_pytest_is_empty(tmp_path):
    assert sys.executable  # sanity
    d = await discover(str(tmp_path / "does-not-exist"))
    assert d["tests"] == []
