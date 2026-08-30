"""Expanded framework detection (P13) + the Run system (P14)."""

from __future__ import annotations

import pytest

from core.runtime.runner import plan
from core.workspace import discover_workspace


def _mk(root, files: dict):
    for name, body in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return discover_workspace(root)


def test_fastapi(tmp_path):
    p = _mk(tmp_path, {"requirements.txt": "fastapi\nuvicorn\npytest\n", "main.py": "app = 1\n"})
    assert "fastapi" in p.frameworks
    assert p.commands["run"] == "uvicorn main:app --reload" and p.run_port == 8000


def test_flask(tmp_path):
    p = _mk(tmp_path, {"requirements.txt": "flask\n", "app.py": "from flask import Flask\n"})
    assert "flask" in p.frameworks and p.run_port == 5000


def test_next_js_and_pm(tmp_path):
    p = _mk(tmp_path, {
        "package.json": '{"dependencies":{"next":"14"},"scripts":{"dev":"next dev","build":"next build"}}',
        "pnpm-lock.yaml": "",
        "tsconfig.json": "{}",
    })
    assert "next.js" in p.frameworks and "pnpm" in p.package_managers
    assert p.commands["run"] == "pnpm run dev" and "typescript" in p.languages


def test_flutter(tmp_path):
    p = _mk(tmp_path, {"pubspec.yaml": "name: x\nflutter:\n  uses-material-design: true\n"})
    assert "flutter" in p.frameworks and p.commands["run"] == "flutter run"


def test_spring_boot(tmp_path):
    p = _mk(tmp_path, {"pom.xml": "<project><dependency>spring-boot-starter</dependency></project>"})
    assert "spring-boot" in p.frameworks and p.commands["run"] == "mvn spring-boot:run"


def test_dotnet(tmp_path):
    p = _mk(tmp_path, {"App.csproj": "<Project/>"})
    assert ".net" in p.frameworks and p.commands["run"] == "dotnet run"


def test_docker_compose_run(tmp_path):
    p = _mk(tmp_path, {"docker-compose.yml": "services: {}"})
    assert p.has_docker and p.commands.get("run") == "docker compose up"


def test_run_plan_falls_back_to_entrypoint(tmp_path):
    _mk(tmp_path, {"main.py": "print(1)\n"})
    rp = plan(str(tmp_path))
    assert rp.command == "python main.py"


def test_run_plan_kinds(tmp_path):
    _mk(tmp_path, {"go.mod": "module m\n"})
    assert plan(str(tmp_path), "build").command == "go build ./..."
    assert plan(str(tmp_path), "test").command == "go test ./..."


@pytest.mark.parametrize("v", [".venv", "venv"])
def test_virtualenv_detected(tmp_path, v):
    (tmp_path / v).mkdir()
    (tmp_path / v / "pyvenv.cfg").write_text("home = x\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    p = discover_workspace(tmp_path)
    assert p.virtualenv == v
