"""计划 16 Task 8:新鲜度检测——file:// 真实 git 仓四态。"""
import subprocess

import pytest

from app.cicd import freshness
from app.config import settings
from app.models import AutomationRepo, Project


@pytest.fixture()
def git_repo(tmp_path, monkeypatch, db_session):
    """裸仓 + 种子提交;返回 (repo 行, 种子工作区路径, 裸仓路径)。"""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(origin)], check=True)
    src = tmp_path / "seed"
    src.mkdir()
    (src / "a.txt").write_text("v1", encoding="utf-8")
    subprocess.run(["git", "-C", str(src), "init", "-q", "-b", "master"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "."], check=True)
    subprocess.run(["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "v1"], check=True)
    subprocess.run(["git", "-C", str(src), "push", "-q", str(origin), "master"], check=True)

    monkeypatch.setattr(settings, "repos_dir", tmp_path / "repos")
    proj = Project(name="fp")
    db_session.add(proj)
    db_session.commit()
    repo = AutomationRepo(project_id=proj.id, kind="web", repo_url=origin.as_uri())
    db_session.add(repo)
    db_session.commit()
    return repo, src, origin


def test_clean_on_branch_not_stale(git_repo):
    repo, src, origin = git_repo
    from app import git_service

    git_service.sync_repo(repo, "master")  # 先 clone 到位
    fresh = freshness.check_freshness(repo, "master")
    assert fresh == {"on_branch": True, "dirty_files": 0, "ahead": 0, "stale": False}


def test_untracked_file_is_stale(git_repo):
    repo, src, origin = git_repo
    from app import git_service

    git_service.sync_repo(repo, "master")
    wc = git_service.working_copy_path(repo)
    (wc / "exported_test.py").write_text("untracked 导出产物", encoding="utf-8")
    fresh = freshness.check_freshness(repo, "master")
    assert fresh["dirty_files"] >= 1 and fresh["stale"] is True


def test_local_commit_ahead_is_stale(git_repo):
    repo, src, origin = git_repo
    from app import git_service

    git_service.sync_repo(repo, "master")
    wc = git_service.working_copy_path(repo)
    (wc / "b.txt").write_text("v2", encoding="utf-8")
    subprocess.run(["git", "-C", str(wc), "add", "."], check=True)
    subprocess.run(["git", "-C", str(wc), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "v2"], check=True)
    fresh = freshness.check_freshness(repo, "master")
    assert fresh["ahead"] == 1 and fresh["stale"] is True


def test_other_branch_reports_on_branch_false(git_repo):
    repo, src, origin = git_repo
    from app import git_service

    git_service.sync_repo(repo, "master")
    fresh = freshness.check_freshness(repo, "release")
    assert fresh["on_branch"] is False and fresh["stale"] is False
