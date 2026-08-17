# tests/test_git_service_read.py
import subprocess
from pathlib import Path

import pytest

from app import git_service
from app.git_service import GitError, working_copy_path, validate_repo_url


def _make_bare_origin(tmp_path: Path) -> Path:
    """造一个 bare 仓库作为 origin,含一个初始 commit。"""
    work = tmp_path / "origin_work"
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=work, check=True)
    (work / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=work, check=True)
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
    return bare


@pytest.fixture
def repos_dir(tmp_path, monkeypatch):
    d = tmp_path / "repos"
    d.mkdir()
    monkeypatch.setattr(git_service.settings, "repos_dir", d)
    return d


def _project(url, token="tok"):
    from app.models import Project
    return Project(id=1, name="p", git_repo_url=url, git_token=token)


def test_validate_repo_url_rejects_non_http():
    with pytest.raises(GitError) as e:
        validate_repo_url("ssh://git@host/repo")
    assert e.value.stage == "url"


def test_validate_repo_url_accepts_https():
    validate_repo_url("https://gitlab.com/g/r.git")  # 不 raise


def test_ensure_repo_clones_when_absent(repos_dir, tmp_path):
    bare = _make_bare_origin(tmp_path)
    proj = _project(f"file:///{bare.as_posix()}")
    wc = git_service.ensure_repo(proj)
    assert wc.exists()
    assert (wc / "README.md").exists()


def test_sync_repo_updates_existing(repos_dir, tmp_path):
    bare = _make_bare_origin(tmp_path)
    proj = _project(f"file:///{bare.as_posix()}")
    r1 = git_service.sync_repo(proj)
    assert r1.cloned is True
    # origin 加新文件后 sync 应 updated
    work = tmp_path / "origin_work"
    (work / "new.txt").write_text("n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "add new"], cwd=work, check=True)
    subprocess.run(["git", "push", "-q", str(bare), "master"], cwd=work, check=True)
    r2 = git_service.sync_repo(proj)
    assert r2.updated is True
    assert (working_copy_path(proj) / "new.txt").exists()


def test_list_files_filters_target(repos_dir, tmp_path):
    bare = _make_bare_origin(tmp_path)
    proj = _project(f"file:///{bare.as_posix()}")
    git_service.sync_repo(proj)
    wc = working_copy_path(proj)
    (wc / "target").mkdir()
    (wc / "target" / "build.o").write_text("x", encoding="utf-8")
    (wc / "src").mkdir()
    (wc / "src" / "A.java").write_text("class A{}", encoding="utf-8")
    tree = git_service.list_files(proj)
    names = [n.name for n in tree.children or []] if tree.is_dir else []
    assert "src" in names
    assert "target" not in names
    assert ".git" not in names


def test_read_file_rejects_traversal(repos_dir, tmp_path):
    bare = _make_bare_origin(tmp_path)
    proj = _project(f"file:///{bare.as_posix()}")
    git_service.sync_repo(proj)
    with pytest.raises(GitError):
        git_service.read_file(proj, "../../etc/passwd")


def test_git_status_reports_added(repos_dir, tmp_path):
    bare = _make_bare_origin(tmp_path)
    proj = _project(f"file:///{bare.as_posix()}")
    git_service.sync_repo(proj)
    wc = working_copy_path(proj)
    (wc / "new.java").write_text("x", encoding="utf-8")
    changes = git_service.git_status(proj)
    assert any(c.path == "new.java" and c.status == "added" for c in changes)


def test_list_remote_branches(repos_dir, tmp_path):
    bare = _make_bare_origin(tmp_path)
    proj = _project(f"file:///{bare.as_posix()}")
    git_service.sync_repo(proj)
    branches = git_service.list_remote_branches(proj)
    assert "master" in branches
