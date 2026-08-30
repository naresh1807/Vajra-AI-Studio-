"""Workspace path-escape protection (master-prompt P5 / P32)."""

from __future__ import annotations

import os
import sys

import pytest

from core.workspace import WorkspaceConflict, WorkspaceError, read_file, write_file
from core.workspace.safepath import PathEscape, is_within, safe_resolve


@pytest.fixture
def ws(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("nested", encoding="utf-8")
    return tmp_path


def test_allows_paths_inside(ws):
    assert safe_resolve(ws, "a.txt") == (ws / "a.txt").resolve()
    assert safe_resolve(ws, "sub/b.txt") == (ws / "sub" / "b.txt").resolve()
    assert safe_resolve(ws, "sub\\b.txt") == (ws / "sub" / "b.txt").resolve()
    assert safe_resolve(ws, "new/deep/file.py")  # non-existent is fine (for writes)


@pytest.mark.parametrize(
    "bad",
    [
        "../evil",
        "../../etc/passwd",
        "sub/../../escape",
        "",
        "x\x00y",
        "a.txt:$DATA",  # NTFS alternate data stream
        "file.txt:hidden",
    ],
)
def test_denies_escapes_and_tricks(ws, bad):
    with pytest.raises(PathEscape):
        safe_resolve(ws, bad)


def test_denies_absolute_outside(ws):
    outside = "C:\\Windows\\system32" if sys.platform == "win32" else "/etc/passwd"
    with pytest.raises(PathEscape):
        safe_resolve(ws, outside)


def test_denies_unc(ws):
    with pytest.raises(PathEscape):
        safe_resolve(ws, "\\\\server\\share\\x")


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="no symlink support")
def test_denies_symlink_escape(ws, tmp_path):
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("TOP SECRET", encoding="utf-8")
    link = ws / "link.txt"
    try:
        os.symlink(secret, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not permitted here")
    with pytest.raises((PathEscape, WorkspaceError)):
        read_file(ws, "link.txt")


def test_is_within_case_insensitive_on_windows(tmp_path):
    d = tmp_path / "Work"
    d.mkdir()
    assert is_within(d, d / "f")
    if sys.platform == "win32":
        assert is_within(str(d).lower(), str(d / "f"))


# -- P9: document-version conflict -----------------------------------
def test_write_rejects_stale_base_sha(ws):
    fc = read_file(ws, "a.txt")
    assert fc.sha256
    # someone edits it underneath us
    (ws / "a.txt").write_text("hello + user edit", encoding="utf-8")
    with pytest.raises(WorkspaceConflict) as ei:
        write_file(ws, "a.txt", "hello + agent edit", base_sha=fc.sha256)
    assert ei.value.current == "hello + user edit"


def test_write_ok_with_current_base_sha(ws):
    fc = read_file(ws, "a.txt")
    res = write_file(ws, "a.txt", "updated", base_sha=fc.sha256)
    assert res.created is False and read_file(ws, "a.txt").content == "updated"


def test_write_without_base_sha_still_works(ws):
    write_file(ws, "a.txt", "no-check", base_sha=None)
    assert read_file(ws, "a.txt").content == "no-check"
