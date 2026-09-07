# tests/test_git_service_push.py
import subprocess
from pathlib import Path

import pytest

from app import git_service
from app.git_service import GitError, PushConflict, NothingToCommit, working_copy_path


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


def test_push_files_reexport_overwrites_tracked_file(repos_dir, tmp_path):
    """再导出覆盖已跟踪文件(RUN.md):调用方(导出流程)先写盘后 push_files,
    工作区带未暂存变更时 pull --rebase 直接拒绝(exit 128)。push_files 必须
    先 add+commit 再 rebase,否则同仓第二次导出永远被误报「与远程冲突」
    (2026-09-07 冒烟:脚本 #19 导出 PushConflict,实际本地与远程零分叉)。"""
    bare = _make_bare_origin(tmp_path)
    proj = _project(bare)
    git_service.sync_repo(proj)
    wc = working_copy_path(proj)
    (wc / "RUN.md").write_text("v1", encoding="utf-8")
    git_service.push_files(proj, ["RUN.md"], "main", "first")
    # 模拟再次导出:同名文件改写后未提交即推
    (wc / "RUN.md").write_text("v2", encoding="utf-8")
    r = git_service.push_files(proj, ["RUN.md"], "main", "second")
    assert r.ok is True
    out = subprocess.run(["git", "show", "origin/main:RUN.md"], cwd=wc,
                         capture_output=True, text=True, check=True)
    assert out.stdout == "v2"


def test_push_pull_connection_error_not_conflict(repos_dir, tmp_path):
    """GitLab 不可达时 pull 失败是连接错误,归 stage=pull 的 GitError;
    不得误报 409「与远程冲突」误导排障(2026-09-07 冒烟:GitLab 容器未启动)。"""
    bare = _make_bare_origin(tmp_path)
    proj = _project(bare)
    git_service.sync_repo(proj)
    wc = working_copy_path(proj)
    (wc / "RUN.md").write_text("v1", encoding="utf-8")
    git_service.push_files(proj, ["RUN.md"], "main", "first")
    # 远程指向不可达端口(模拟 GitLab 未启动),内容有变更使流程走到 pull
    subprocess.run(["git", "remote", "set-url", "origin", "http://127.0.0.1:59999/x.git"],
                   cwd=wc, check=True)
    (wc / "RUN.md").write_text("v2", encoding="utf-8")
    with pytest.raises(GitError) as ei:
        git_service.push_files(proj, ["RUN.md"], "main", "second")
    assert ei.value.stage == "pull"


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
    # 本地未提交改同一文件(与导出流程同形:先写盘),提交后 rebase 撞远程改动 → 真冲突
    (wc / "T.java").write_text("local-change", encoding="utf-8")
    with pytest.raises(PushConflict):
        git_service.push_files(proj, ["T.java"], "dev", "conflict")
    # rebase 应已 abort,无残留(本地 conflict 提交保留在分支上)
    assert "rebase in progress" not in subprocess.run(
        ["git", "status"], cwd=wc, capture_output=True, text=True, check=True).stdout
