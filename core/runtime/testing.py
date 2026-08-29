"""Test discovery + run for the Studio test explorer (manual v3.0 sec: testing).

pytest is first-class (parsed from ``-v`` output); Node projects with a test
script fall back to running that script and reporting the exit code.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

_PYTEST_LINE = re.compile(
    r"^(?P<id>[^\s:]+(?:::[^\s]+)+)\s+(?P<outcome>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)"
)
_SUMMARY = re.compile(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)")
_MAX_OUTPUT = 200_000


@dataclass
class TestCase:
    id: str
    outcome: str = "unknown"   # passed | failed | error | skipped | unknown


@dataclass
class TestRun:
    framework: str
    ok: bool
    cases: list[TestCase] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=dict)
    duration_s: float = 0.0
    output: str = ""

    def as_dict(self) -> dict:
        return {
            "framework": self.framework, "ok": self.ok,
            "cases": [c.__dict__ for c in self.cases],
            "totals": self.totals, "duration_s": self.duration_s, "output": self.output,
        }


def detect_framework(root: str) -> str:
    base = Path(root)
    if (base / "pytest.ini").exists() or (base / "pyproject.toml").exists() or (base / "tests").is_dir() \
            or any(base.glob("test_*.py")) or any(base.glob("*/test_*.py")):
        return "pytest"
    pkg = base / "package.json"
    if pkg.exists():
        try:
            scripts = json.loads(pkg.read_text("utf-8")).get("scripts", {})
            if "test" in scripts:
                return "node"
        except ValueError:
            pass
    return "unknown"


async def _run(argv: list[str], cwd: str, timeout: float) -> tuple[int | None, str, float]:
    loop = asyncio.get_running_loop()
    start = loop.time()
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, out.decode("utf-8", "replace")[:_MAX_OUTPUT], round(loop.time() - start, 1)
    except (OSError, TimeoutError) as exc:
        return None, f"{type(exc).__name__}: {exc}", round(loop.time() - start, 1)


async def discover(root: str) -> dict:
    fw = detect_framework(root)
    if fw != "pytest":
        return {"framework": fw, "tests": []}
    rc, out, _ = await _run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "--no-header"], root, 120
    )
    ids = [ln.strip() for ln in out.splitlines() if "::" in ln and not ln.startswith(" ")]
    return {"framework": "pytest", "tests": sorted(set(ids))}


async def run_tests(root: str, node_ids: list[str] | None = None, timeout: float = 900) -> TestRun:
    fw = detect_framework(root)
    if fw == "node":
        rc, out, dur = await _run(["npm", "test", "--silent"], root, timeout)
        return TestRun("node", ok=rc == 0, duration_s=dur, output=out)
    if fw != "pytest":
        return TestRun("unknown", ok=False, output="no test framework detected")

    argv = [sys.executable, "-m", "pytest", "-v", "--no-header", "--tb=short", "-p", "no:cacheprovider"]
    argv += list(node_ids) if node_ids else []
    rc, out, dur = await _run(argv, root, timeout)

    cases: list[TestCase] = []
    for line in out.splitlines():
        m = _PYTEST_LINE.match(line.strip())
        if m:
            oc = m.group("outcome").lower()
            cases.append(TestCase(m.group("id"), {"xfail": "skipped", "xpass": "passed"}.get(oc, oc)))
    totals: dict[str, int] = {}
    tail = out.splitlines()[-1] if out.splitlines() else ""
    for n, kind in _SUMMARY.findall(tail):
        totals[kind.rstrip("s")] = int(n)
    return TestRun("pytest", ok=rc == 0, cases=cases, totals=totals, duration_s=dur, output=out)
