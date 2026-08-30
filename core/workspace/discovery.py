"""Project profiling (master-prompt P13). On first open, detect stack /
framework / package manager / commands / entrypoints and cache them under
.vajra/ so we don't re-scan or over-feed the model.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class WorkspaceProfile(BaseModel):
    root: str
    languages: list[str] = []
    frameworks: list[str] = []
    package_managers: list[str] = []
    entrypoints: list[str] = []
    commands: dict[str, str] = {}   # run / build / test / lint / format
    run_port: int | None = None
    database: str | None = None
    virtualenv: str | None = None
    test_runner: str | None = None
    linter: str | None = None
    formatter: str | None = None
    has_docker: bool = False
    has_git: bool = False
    important_dirs: list[str] = []

    def save(self) -> Path:
        vajra = Path(self.root) / ".vajra"
        vajra.mkdir(exist_ok=True)
        path = vajra / "project.json"
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return path


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _text(path: Path, limit: int = 20_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _first(root: Path, *names: str) -> str | None:
    for n in names:
        if (root / n).exists():
            return n
    return None


def _python(root: Path, p: WorkspaceProfile) -> None:
    pyproject = _text(root / "pyproject.toml")
    reqs = _text(root / "requirements.txt").lower()
    haystack = (pyproject + "\n" + reqs).lower()
    if not (pyproject or reqs or any(root.glob("*.py"))):
        return
    p.languages.append("python")

    p.package_managers.append(
        "poetry" if "[tool.poetry]" in pyproject
        else "uv" if (root / "uv.lock").exists()
        else "pipenv" if (root / "Pipfile").exists()
        else "pip"
    )
    for v in (".venv", "venv", "env"):
        d = root / v
        if (d / "pyvenv.cfg").exists() or (d / "bin" / "python").exists() or (d / "Scripts").is_dir():
            p.virtualenv = v
            break

    # pytest is the default; only fall back to unittest with clear evidence
    unittest_only = (
        "pytest" not in haystack
        and not (root / "pytest.ini").exists()
        and any("unittest" in _text(f, 2000) for f in list(root.glob("**/test*.py"))[:20])
    )
    p.test_runner = "unittest" if unittest_only else "pytest"
    p.commands["test"] = "python -m unittest -q" if unittest_only else "python -m pytest -q"
    p.linter = "ruff" if "ruff" in haystack else "flake8" if "flake8" in haystack else None
    p.formatter = "ruff" if "ruff" in haystack else "black" if "black" in haystack else None
    if p.linter:
        p.commands["lint"] = "ruff check ." if p.linter == "ruff" else "flake8"
    if p.formatter:
        p.commands["format"] = "ruff format ." if p.formatter == "ruff" else "black ."

    entry = _first(root, "manage.py", "main.py", "app.py", "api/main.py", "src/main.py", "wsgi.py", "asgi.py")
    if entry:
        p.entrypoints.append(entry)

    if (root / "manage.py").exists():
        p.frameworks.append("django")
        p.commands["run"] = "python manage.py runserver"
        p.run_port = 8000
        if next(root.glob("**/settings.py"), None):
            p.database = p.database or "sqlite"
    elif "fastapi" in haystack or "uvicorn" in haystack:
        p.frameworks.append("fastapi")
        mod = "main:app" if (root / "main.py").exists() else (
            "app:app" if (root / "app.py").exists() else "app.main:app"
        )
        p.commands["run"] = f"uvicorn {mod} --reload"
        p.run_port = 8000
    elif "flask" in haystack:
        p.frameworks.append("flask")
        has_app = (root / "app.py").exists()
        p.commands["run"] = "flask --app app run --debug" if has_app else "python -m flask run"
        p.run_port = 5000
    elif entry and "run" not in p.commands:
        p.commands["run"] = f"python {entry}"

    if "sqlalchemy" in haystack or "psycopg" in haystack:
        p.database = p.database or "postgres"


def _node(root: Path, p: WorkspaceProfile) -> None:
    pkg = root / "package.json"
    if not pkg.exists():
        return
    data = _read_json(pkg)
    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    scripts = data.get("scripts", {})
    p.languages.append("typescript" if (root / "tsconfig.json").exists() else "javascript")

    pm = (
        "pnpm" if (root / "pnpm-lock.yaml").exists()
        else "yarn" if (root / "yarn.lock").exists()
        else "bun" if (root / "bun.lockb").exists()
        else "npm"
    )
    p.package_managers.append(pm)
    x = f"{pm} run" if pm != "npm" else "npm run"

    for name, fw in (
        ("next", "next.js"), ("nuxt", "nuxt"), ("@angular/core", "angular"),
        ("svelte", "svelte"), ("vue", "vue"), ("react", "react"), ("vite", "vite"),
        ("@nestjs/core", "nestjs"), ("express", "express"), ("fastify", "fastify"),
    ):
        if name in deps:
            p.frameworks.append(fw)

    p.test_runner = next((t for t in ("vitest", "jest", "mocha", "playwright") if t in deps), None)
    for key, mapped in (("dev", "run"), ("start", "run"), ("build", "build"),
                        ("test", "test"), ("lint", "lint"), ("format", "format")):
        if key in scripts and mapped not in p.commands:
            p.commands[mapped] = f"{x} {key}"
    if "run" not in p.commands and (root / "server.js" or root / "index.js"):
        p.commands.setdefault("run", f"{pm} start" if pm != "npm" else "npm start")
    if "next.js" in p.frameworks or "vite" in p.frameworks or "nuxt" in p.frameworks:
        p.run_port = 3000 if "next.js" in p.frameworks or "nuxt" in p.frameworks else 5173


def _other(root: Path, p: WorkspaceProfile) -> None:
    if (root / "Cargo.toml").exists():
        p.languages.append("rust")
        p.package_managers.append("cargo")
        p.commands.setdefault("build", "cargo build")
        p.commands.setdefault("test", "cargo test")
        p.commands.setdefault("run", "cargo run")

    if (root / "go.mod").exists():
        p.languages.append("go")
        p.commands.setdefault("build", "go build ./...")
        p.commands.setdefault("test", "go test ./...")
        p.commands.setdefault("run", "go run .")

    if (root / "pom.xml").exists():
        p.languages.append("java")
        p.package_managers.append("maven")
        if "spring-boot" in _text(root / "pom.xml"):
            p.frameworks.append("spring-boot")
            p.commands.setdefault("run", "mvn spring-boot:run")
            p.run_port = 8080
        p.commands.setdefault("build", "mvn package")
        p.commands.setdefault("test", "mvn test")
    elif _first(root, "build.gradle", "build.gradle.kts"):
        p.languages.append("java/kotlin")
        p.package_managers.append("gradle")
        p.commands.setdefault("build", "gradle build")
        p.commands.setdefault("test", "gradle test")

    csproj = next(root.glob("*.csproj"), None) or next(root.glob("*.sln"), None)
    if csproj:
        p.languages.append("csharp")
        p.frameworks.append(".net")
        p.commands.setdefault("run", "dotnet run")
        p.commands.setdefault("build", "dotnet build")
        p.commands.setdefault("test", "dotnet test")

    pubspec = _text(root / "pubspec.yaml")
    if pubspec and "flutter:" in pubspec:
        p.languages.append("dart")
        p.frameworks.append("flutter")
        p.commands.setdefault("run", "flutter run")
        p.commands.setdefault("test", "flutter test")
        p.commands.setdefault("build", "flutter build apk")
    elif pubspec:
        p.languages.append("dart")
        p.commands.setdefault("run", "dart run")

    if (root / "CMakeLists.txt").exists():
        p.languages.append("c/c++")
        p.commands.setdefault("build", "cmake -B build && cmake --build build")
    elif _first(root, "Makefile", "makefile"):
        p.commands.setdefault("build", "make")


def discover_workspace(root: str | Path) -> WorkspaceProfile:
    root = Path(root).resolve()

    cached = root / ".vajra" / "project.json"
    if cached.exists():
        data = _read_json(cached)
        if data:
            return WorkspaceProfile.model_validate(data)

    p = WorkspaceProfile(root=str(root))
    p.has_git = (root / ".git").exists()
    p.has_docker = bool(_first(root, "Dockerfile", "docker-compose.yml", "compose.yaml"))
    if p.has_docker and _first(root, "docker-compose.yml", "compose.yaml"):
        p.commands.setdefault("run", "docker compose up")

    _python(root, p)
    _node(root, p)
    _other(root, p)

    _interesting = {"src", "core", "api", "app", "apps", "lib", "tests", "test",
                    "server", "frontend", "backend", "packages", "cmd", "internal"}
    p.important_dirs = [d.name for d in sorted(root.iterdir()) if d.is_dir() and d.name in _interesting]

    # de-dupe, keep order
    for fld in ("languages", "frameworks", "package_managers", "entrypoints"):
        seen: list = []
        for x in getattr(p, fld):
            if x not in seen:
                seen.append(x)
        setattr(p, fld, seen)

    p.save()
    return p
