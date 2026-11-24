import subprocess

import pytest

from engine.gitsync import checkpoint


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    work = tmp_path / "work"
    git(tmp_path, "clone", "-q", str(remote), str(work))
    git(work, "config", "user.name", "t")
    git(work, "config", "user.email", "t@t")
    (work / "README").write_text("x")
    git(work, "add", ".")
    git(work, "commit", "-qm", "init")
    git(work, "push", "-q", "origin", "HEAD:main")
    return work, remote


def test_checkpoint_pushes_ledger(repo):
    work, remote = repo
    (work / "state" / "a").mkdir(parents=True)
    (work / "state" / "a" / "ledger.jsonl").write_text('{"event":"publishing"}\n')
    checkpoint(work)
    assert "ledger.jsonl" in git(remote, "ls-tree", "-r", "--name-only", "main")


def test_checkpoint_raises_when_push_fails(repo):
    work, remote = repo
    git(work, "remote", "set-url", "origin", str(work.parent / "missing.git"))
    (work / "state").mkdir()
    (work / "state" / "l.jsonl").write_text("x\n")
    with pytest.raises(RuntimeError):
        checkpoint(work)


def test_checkpoint_noop_when_nothing_changed(repo):
    work, _ = repo
    checkpoint(work)  # nothing staged: no error
