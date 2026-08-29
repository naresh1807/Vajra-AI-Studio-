import subprocess

import pytest

from core.runtime import git as g


def _run(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    _run(tmp_path, "init", "-q")
    _run(tmp_path, "config", "user.email", "t@t")
    _run(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.txt").write_text("one\n")
    _run(tmp_path, "add", "-A")
    _run(tmp_path, "commit", "-qm", "init")
    return tmp_path


async def test_status_detects_changes(repo):
    (repo / "a.txt").write_text("one\ntwo\n")
    (repo / "b.txt").write_text("new\n")
    st = await g.status(str(repo))
    assert st.is_repo and st.branch in ("master", "main")
    paths = {f.path: f for f in st.files}
    assert paths["a.txt"].unstaged and paths["a.txt"].status == "modified"
    assert paths["b.txt"].status == "untracked"


async def test_stage_commit(repo):
    (repo / "a.txt").write_text("changed\n")
    await g.stage(str(repo), ["a.txt"])
    st = await g.status(str(repo))
    assert next(f for f in st.files if f.path == "a.txt").staged
    sha = await g.commit(str(repo), "update a")
    assert len(sha) >= 6
    assert (await g.status(str(repo))).files == []


async def test_checkpoint_and_restore(repo):
    (repo / "a.txt").write_text("v2\n")
    cp = await g.checkpoint(str(repo), "before risky change")
    assert cp["tag"].startswith("vajra/")
    (repo / "a.txt").write_text("v3-broken\n")
    (repo / "c.txt").write_text("junk\n")
    await g.restore(str(repo), cp["tag"])
    assert (repo / "a.txt").read_text() == "v2\n"
    assert not (repo / "c.txt").exists()


async def test_restore_rejects_non_vajra_tag(repo):
    with pytest.raises(g.GitError):
        await g.restore(str(repo), "HEAD~1")


async def test_discard_file(repo):
    (repo / "a.txt").write_text("mistake\n")
    await g.discard(str(repo), "a.txt")
    assert (repo / "a.txt").read_text() == "one\n"
