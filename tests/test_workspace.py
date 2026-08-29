from core.workspace import discover_workspace


def test_detects_python(tmp_workspace):
    p = discover_workspace(tmp_workspace)
    assert "python" in p.languages
    assert p.commands.get("test", "").startswith("python -m pytest")
    assert (tmp_workspace / ".vajra" / "project.json").exists()


def test_detects_node(tmp_path):
    (tmp_path / "package.json").write_text(
        '{"dependencies":{"react":"18"},"scripts":{"dev":"vite","build":"vite build"}}',
        encoding="utf-8",
    )
    p = discover_workspace(tmp_path)
    assert "react" in p.frameworks
    assert p.commands.get("run") == "npm run dev"


def test_profile_is_cached(tmp_workspace):
    first = discover_workspace(tmp_workspace)
    (tmp_workspace / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    second = discover_workspace(tmp_workspace)
    assert second.languages == first.languages  # served from cache, rust not picked up
