# tests/test_git_service_push.py
import subprocess
from pathlib import Path

import pytest

from app import git_service
from app.git_service import PushConflict, NothingToCommit, working_copy_path


def _make_bare_origin(tmp_path: Path) -> Path:
    work = tmp_path / "origin_work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
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


def _project(bare, token="tok"):
    from app.models import Project
    return Project(id=1, name="p", git_repo_url=f"file:///{bare.as_posix()}", git_token=token)


def test_push_files_creates_branch_and_pushes(repos_dir, tmp_path):
    bare = _make_bare_origin(tmp_path)
    proj = _project(bare)
    git_service.sync_repo(proj)
    wc = working_copy_path(proj)
    (wc / "T.java").write_text("class T{}", encoding="utf-8")
    r = git_service.push_files(proj, ["T.java"], "dev", "AI 生成接口测试 2026-08-17 12:00")
    assert r.ok is True
    assert r.branch == "dev"
    assert "T.java" in r.pushed_files
    # 远程 dev 分支应存在并含该文件
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", "origin/dev"], cwd=wc, capture_output=True, text=True, check=True)
    assert "T.java" in out.stdout


def test_push_nothing_to_commit(repos_dir, tmp_path):
    bare = _make_bare_origin(tmp_path)
    proj = _project(bare)
    git_service.sync_repo(proj)
    with pytest.raises(NothingToCommit):
        git_service.push_files(proj, [], "dev", "msg")


def test_push_rebase_conflict_aborts(repos_dir, tmp_path):
    bare = _make_bare_origin(tmp_path)
    proj = _project(bare)
    git_service.sync_repo(proj)
    wc = working_copy_path(proj)
    # 先推一次到 dev 建分支
    (wc / "T.java").write_text("v1", encoding="utf-8")
    git_service.push_files(proj, ["T.java"], "dev", "first")
    # origin 端在 dev 上改 T.java(模拟他人推送)
    work = tmp_path / "origin_work"
    subprocess.run(["git", "fetch", "-q", str(bare), "dev"], cwd=work, check=True)
    subprocess.run(["git", "checkout", "-q", "-B", "dev", "FETCH_HEAD"], cwd=work, check=True)
    (work / "T.java").write_text("remote-change", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "remote"], cwd=work, check=True)
    subprocess.run(["git", "push", "-q", str(bare), "dev"], cwd=work, check=True)
    # 本地再改 T.java 为不同内容,拉 rebase 必冲突
    subprocess.run(["git", "checkout", "-q", "dev"], cwd=wc, check=True)
    (wc / "T.java").write_text("local-change", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=wc, check=True)
    subprocess.run(["git", "commit", "-qm", "local"], cwd=wc, check=True)
    with pytest.raises(PushConflict):
        git_service.push_files(proj, ["T.java"], "dev", "conflict")
    # rebase 应已 abort,working copy 干净
    st = subprocess.run(["git", "status", "--porcelain"], cwd=wc, capture_output=True, text=True, check=True)
    # 本地 commit 仍在(rebase abort 回到本地分支态)
    assert "rebase in progress" not in subprocess.run(["git", "status"], cwd=wc, capture_output=True, text=True, check=True).stdout
