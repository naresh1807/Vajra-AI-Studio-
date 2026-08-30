"""Project playbooks: when a goal implies a known kind of project (a Flutter
Android app, a FastAPI service, a React site, ...), inject the canonical file
layout + scaffold/build/run/test commands into the agents' context.

Without this, a hosted model asked to "build an Android app" takes the cheapest
valid reading and writes a single file. A playbook tells the planner to scaffold
the real project first and the coder exactly which files a complete app needs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


def slugify(text: str) -> str:
    """A valid lowercase package/identifier slug derived from the goal."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    stop = {"a", "an", "the", "app", "application", "build", "make", "create", "me", "my",
            "please", "android", "flutter", "mobile", "ios", "with", "that", "for", "to"}
    kept = [w for w in words if w not in stop][:3] or ["app"]
    slug = "_".join(kept)
    if slug[0].isdigit():
        slug = "app_" + slug
    return slug[:40]


@dataclass(frozen=True)
class Playbook:
    name: str
    keywords: tuple[str, ...]
    layout: str
    guidance: str
    scaffold: str = ""   # a shell command that creates the skeleton, or ""
    build: str = ""
    run: str = ""
    test: str = ""

    def matches(self, goal: str) -> bool:
        g = goal.lower()
        return any(k in g for k in self.keywords)

    def render(self, goal: str) -> str:
        slug = slugify(goal)
        parts = [f"# Project playbook — {self.name}", self.guidance.strip()]
        if self.scaffold:
            parts.append(
                "Scaffold FIRST, before writing code (run once, via the tester/runner):\n"
                f"    {self.scaffold.format(slug=slug)}"
            )
        parts.append("Canonical layout:\n" + self.layout.rstrip())
        cmds = [(lbl, c) for lbl, c in
                (("run", self.run), ("build", self.build), ("test", self.test)) if c]
        if cmds:
            parts.append("Commands:\n" + "\n".join(f"    {lbl}: {c}" for lbl, c in cmds))
        return "\n\n".join(parts)


_PLAYBOOKS: tuple[Playbook, ...] = (
    Playbook(
        name="Flutter Android app",
        keywords=("flutter", "android app", "android application", ".apk", "apk",
                  "mobile app", "ios app", "android game"),
        scaffold="flutter create --project-name {slug} --platforms android .",
        run="flutter run",
        build="flutter build apk --release",
        test="flutter test",
        layout=(
            "  pubspec.yaml           # name + every dependency you import (http, provider, …)\n"
            "  lib/main.dart          # void main() => runApp(...); MaterialApp; the home screen\n"
            "  lib/<screen>.dart      # one file per screen / model / service\n"
            "  test/widget_test.dart  # at least one widget test\n"
            "  android/               # created by `flutter create` — never hand-write it"
        ),
        guidance=(
            "This is a Flutter app — NOT a single Python or Dart file. Produce a COMPLETE, "
            "buildable project. Run the scaffold command first so `android/` and the Gradle "
            "files exist, then edit pubspec.yaml and write the Dart UI across lib/. Use "
            "Material 3 and a StatefulWidget for anything interactive. Add every package you "
            "import to pubspec.yaml's dependencies. Done = `flutter analyze` clean and at "
            "least one passing `flutter test`."
        ),
    ),
    Playbook(
        name="Native Android (Kotlin) app",
        keywords=("kotlin android", "native android", "jetpack compose", "gradle android"),
        run="./gradlew installDebug",
        build="./gradlew assembleDebug",
        test="./gradlew test",
        layout=(
            "  settings.gradle(.kts), build.gradle(.kts)      # root + :app module\n"
            "  app/src/main/AndroidManifest.xml\n"
            "  app/src/main/java/<pkg>/MainActivity.kt\n"
            "  app/src/main/res/layout/ , res/values/strings.xml\n"
            "  gradle/wrapper/ + gradlew                       # the wrapper"
        ),
        guidance=(
            "A native Android app needs a full Gradle project: the manifest, an Activity, "
            "resources, and the Gradle wrapper — not one file. Prefer Jetpack Compose for UI."
        ),
    ),
    Playbook(
        name="FastAPI service",
        keywords=("fastapi", "rest api", "web api", "backend api"),
        run="uvicorn app.main:app --reload",
        test="pytest -q",
        layout=(
            "  pyproject.toml / requirements.txt   # fastapi, uvicorn, …\n"
            "  app/main.py                         # FastAPI() app + routes\n"
            "  app/models.py , app/routers/*.py    # split by concern\n"
            "  tests/test_api.py                   # TestClient tests"
        ),
        guidance="Split routes into routers; add a health route and pytest TestClient tests.",
    ),
    Playbook(
        name="React + Vite site",
        keywords=("react app", "react site", "vite react", "frontend app", "web app"),
        scaffold="npm create vite@latest . -- --template react",
        run="npm run dev",
        build="npm run build",
        test="npm test",
        layout=(
            "  package.json, vite.config.js\n"
            "  index.html, src/main.jsx, src/App.jsx\n"
            "  src/components/*.jsx"
        ),
        guidance="Scaffold with Vite, then build the components. Add deps to package.json.",
    ),
)


def detect_playbook(goal: str) -> Playbook | None:
    """The most specific playbook whose keywords appear in the goal, if any."""
    matches = [p for p in _PLAYBOOKS if p.matches(goal)]
    if not matches:
        return None
    # prefer the playbook with the longest matching keyword (most specific)
    g = goal.lower()
    return max(matches, key=lambda p: max((len(k) for k in p.keywords if k in g), default=0))


def playbook_for(goal: str) -> str:
    """Rendered playbook text for a goal, or '' when none applies."""
    pb = detect_playbook(goal)
    return pb.render(goal) if pb else ""
