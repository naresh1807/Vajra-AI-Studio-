import pytest

from core.runtime import format as fmt


async def test_ruff_formats_python(tmp_path):
    ugly = "x = {  'a':1,'b':2 }\ndef f( a,b ):\n  return a+b\n"
    out = await fmt.format_document(str(tmp_path), "m.py", ugly, "python")
    assert "def f(a, b):" in out
    assert out != ugly


async def test_idempotent(tmp_path):
    src = 'def f(a, b):\n    return a + b\n'
    once = await fmt.format_document(str(tmp_path), "m.py", src, "python")
    twice = await fmt.format_document(str(tmp_path), "m.py", once, "python")
    assert once == twice


async def test_unsupported_language(tmp_path):
    with pytest.raises(fmt.FormatUnavailable):
        await fmt.format_document(str(tmp_path), "x.rs", "fn main(){}", "rust")


@pytest.mark.skipif(not fmt._PRETTIER.exists(), reason="prettier not installed")
async def test_prettier_formats_json(tmp_path):
    out = await fmt.format_document(str(tmp_path), "x.json", '{"a":1,"b":  2}', "json")
    assert out.strip() == '{ "a": 1, "b": 2 }'
