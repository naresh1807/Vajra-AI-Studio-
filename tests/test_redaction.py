"""P20 — secrets are masked before anything reaches the model."""

from __future__ import annotations

from core.security.redaction import is_sensitive_path, redact_secrets
from core.tools import ToolCall, ToolContext, build_default_registry


def test_masks_inline_assignments_and_vendor_keys():
    src = (
        "DB_URL = postgres://ok\n"
        "OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwxyz012345\n"
        "x = 'nvapi-ABCDEFGHIJKLMNOP_qrstuvwxyz-123456'\n"
        "def add(a, b):\n    return a + b\n"
    )
    out, n = redact_secrets(src)
    assert n >= 2
    assert "sk-abcdefghijklmnopqrstuvwxyz012345" not in out
    assert "nvapi-ABCDEFGHIJKLMNOP" not in out
    assert "def add(a, b):" in out  # code structure preserved


def test_pem_block_and_sensitive_paths():
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\n-----END RSA PRIVATE KEY-----\n"
    assert "PRIVATE KEY" not in redact_secrets(pem)[0].replace("REDACTED", "")
    assert is_sensitive_path("proj/.env")
    assert is_sensitive_path("deploy/id_rsa")
    assert is_sensitive_path("certs/server.pem")
    assert not is_sensitive_path("src/env_utils.py")


def test_no_false_positive_on_plain_code():
    src = "def tokenize(s):\n    return s.split()\n\nsecret_sauce = compute()\n"
    out, n = redact_secrets(src)
    assert n == 0 and out == src


async def test_read_file_tool_masks_dotenv(tmp_path):
    (tmp_path / ".env").write_text("NVIDIA_API_KEY=nvapi-supersecretvalue1234567890abc\n", encoding="utf-8")
    reg = build_default_registry()
    ctx = ToolContext(workspace_root=str(tmp_path))
    r = await reg.execute(ToolCall(tool_name="read_file", arguments={"path": ".env"}), ctx, approved=True)
    assert r.success
    assert "nvapi-supersecretvalue1234567890abc" not in r.stdout
    assert "REDACTED" in r.stdout
