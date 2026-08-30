"""Mask secrets before they reach the model or the UI (manual v3.0 PRIORITY 20).

The agent legitimately reads project files; some of them (.env, key files,
config with inline credentials) contain secrets that must never be sent to a
model provider or shown in an AI log. This masks the values while keeping the
surrounding structure so the model still sees "there is an API key here".
"""

from __future__ import annotations

import re

MASK = "***REDACTED***"

# High-signal filenames whose entire contents are treated as sensitive.
_SENSITIVE_NAMES = re.compile(
    r"(?i)(^|[/\\])("
    r"\.env(\.[\w.-]+)?|"
    r"id_(rsa|dsa|ecdsa|ed25519)|"
    r"[\w.-]*\.pem|[\w.-]*\.key|[\w.-]*\.pfx|[\w.-]*\.p12|"
    r"credentials(\.json)?|\.npmrc|\.pypirc|\.netrc|"
    r"[\w.-]*service-account[\w.-]*\.json|[\w.-]*secrets?\.(ya?ml|json|toml)"
    r")$"
)

# (pattern, keep-prefix-group). keep=0 -> replace whole match with MASK;
# keep=1 -> keep group(1) then MASK.
_RULES: list[tuple[re.Pattern[str], int]] = [
    (re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ), 0),
    (re.compile(
        r"(?m)^(\s*(?:export\s+)?[A-Za-z0-9_]*"
        r"(?:KEY|TOKEN|SECRET|CREDENTIAL|CREDENTIALS|DSN"
        r"|(?i:password|passwd|api[_-]?key|access[_-]?key|private[_-]?key|auth[_-]?token))"
        r"[A-Za-z0-9_]*\s*[:=]\s*)['\"]?([A-Za-z0-9][A-Za-z0-9._\-/+~=:]{3,})['\"]?\s*$"
    ), 1),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?([A-Za-z0-9._\-/+=]{12,})"), 1),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), 0),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), 0),
    (re.compile(r"\bnvapi-[A-Za-z0-9_\-]{20,}\b"), 0),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), 0),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), 0),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), 0),
]


def is_sensitive_path(path: str | None) -> bool:
    return bool(path) and bool(_SENSITIVE_NAMES.search(path.replace("\\", "/")))


def redact_secrets(text: str, path: str | None = None) -> tuple[str, int]:
    """Return (masked_text, number_of_masks). Whole-file mask for key/.env files."""
    if not text:
        return text, 0
    if is_sensitive_path(path):
        lines = text.splitlines()
        return (
            f"[{MASK}: {len(lines)} lines of a sensitive file ({path}) "
            "withheld from the model]",
            1,
        )
    n = 0
    out = text
    for pat, keep in _RULES:
        def _sub(m: re.Match[str], _keep: int = keep) -> str:
            nonlocal n
            n += 1
            return (m.group(1) + MASK) if _keep else MASK

        out = pat.sub(_sub, out)
    return out, n
