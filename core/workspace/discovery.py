"""Lightweight project profiling. On first open, detect stack / commands / entrypoints
and cache them under .vajra/ so we don't re-scan or over-feed the model.
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
    commands: dict[str, str] = {}
    database: str | None = None
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


def discover_workspace(root: str | Path) -> WorkspaceProfile:
    root = Path(root).resolve()
    profile = WorkspaceProfile(root=str(root))

    cached = root / ".vajra" / "project.json"
    if cached.exists():
        data = _read_json(cached)
        if data:
            return WorkspaceProfile.model_validate(data)

    profile.has_git = (root / ".git").exists()
    profile.has_docker = any((root / f).exists() for f in ("Dockerfile", "docker-compose.yml"))

    if (root / "pyproject.toml").exists() or (root / "requirements.txt").exists():
        profile.languages.append("python")
        profile.package_managers.append("pip")
        profile.commands["test"] = "python -m pytest -q"
        for cand in ("main.py", "app.py", "manage.py", "api/main.py"):
            if (root / cand).exists():
                profile.entrypoints.append(cand)
        if (root / "manage.py").exists():
            profile.frameworks.append("django")
            profile.commands["run"] = "python manage.py runserver"
        if list(root.glob("**/settings.py"))[:1]:
            profile.database = profile.database or "sqlite"

    pkg = root / "package.json"
    if pkg.exists():
        data = _read_json(pkg)
        deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
        profile.languages.append("javascript/typescript")
        profile.package_managers.append(
            "pnpm" if (root / "pnpm-lock.yaml").exists()
            else "yarn" if (root / "yarn.lock").exists()
            else "npm"
        )
        for name, fw in (("next", "next.js"), ("react", "react"), ("vue", "vue"), ("vite", "vite"),
                         ("express", "express"), ("fastify", "fastify")):
            if name in deps:
                profile.frameworks.append(fw)
        scripts = data.get("scripts", {})
        _script_map = {"dev": "run", "start": "run", "build": "build", "test": "test", "lint": "lint"}
        for key, mapped in _script_map.items():
            if key in scripts and mapped not in profile.commands:
                profile.commands[mapped] = f"npm run {key}"

    if (root / "Cargo.toml").exists():
        profile.languages.append("rust")
        profile.package_managers.append("cargo")
        profile.commands.setdefault("build", "cargo build")
        profile.commands.setdefault("test", "cargo test")

    if (root / "go.mod").exists():
        profile.languages.append("go")
        profile.commands.setdefault("build", "go build ./...")
        profile.commands.setdefault("test", "go test ./...")

    _interesting = {
        "src", "core", "api", "app", "apps", "lib", "tests",
        "server", "frontend", "backend",
    }
    profile.important_dirs = [
        d.name for d in sorted(root.iterdir()) if d.is_dir() and d.name in _interesting
    ]

    profile.save()
    return profile
