"""P32 edge cases for workspace file reads: huge files truncate, binary files
are flagged and never silently corrupted on a round-trip."""

from __future__ import annotations

from core.workspace.files import _MAX_READ_BYTES, read_file


def test_huge_file_is_truncated_not_loaded_whole(tmp_path):
    big = tmp_path / "big.log"
    big.write_bytes(b"x" * (_MAX_READ_BYTES + 50_000))
    fc = read_file(tmp_path, "big.log")
    assert fc.truncated is True
    assert len(fc.content) <= _MAX_READ_BYTES
    assert fc.bytes == _MAX_READ_BYTES + 50_000


def test_binary_file_is_flagged(tmp_path):
    (tmp_path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00")
    fc = read_file(tmp_path, "logo.png")
    assert fc.binary is True


def test_text_file_is_not_flagged_binary(tmp_path):
    (tmp_path / "a.py").write_bytes(b"print('hi')\n")
    fc = read_file(tmp_path, "a.py")
    assert fc.binary is False
    assert fc.content == "print('hi')\n"
