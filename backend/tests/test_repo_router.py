# tests/test_repo_router.py
import subprocess
from pathlib import Path

import pytest

from app import git_service


def _make_bare_origin(tmp_path):
    work = tmp_path / "origin_work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=work, check=True)
    (work / "README.md").write_text("hi", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=work, check=True)
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
    return bare


@pytest.fixture
def repos_dir(tmp_path, monkeypatch):
    d = tmp_path / "repos"
    d.mkdir()
    monkeypatch.setattr(git_service.settings, "repos_dir", d)
    return d


@pytest.fixture(autouse=True)
def _clean_automation_repos():
    """计划 11 Task 2(方案 B,用户批准):repo 端点改为按 AutomationRepo 行解析。
    conftest._TABLES 未含 automation_repos,projects 被 TRUNCATE 复位自增后 id 复用,
    残留行会串项目(与 tests/test_automation_repo.py 同款清理)。"""
    yield
    from sqlalchemy import text

    from app.database import SessionLocal

    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        session.execute(text("TRUNCATE TABLE automation_repos"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        session.commit()
    finally:
        session.close()


def _seed_api_repo(db, project):
    """直接建 Project(git_repo_url=...) 的用例补种 kind=api 行,断言不变。"""
    from app.models import AutomationRepo

    row = AutomationRepo(project_id=project.id, kind="api", repo_url=project.git_repo_url, repo_token=project.git_token)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _admin_headers(client, db_session):
    """Task 7 补鉴权:bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。
    原断言语义不变,仅补鉴权头。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


# Issue D: tests/conftest.py 无 db_session fixture,改用 SessionLocal() 直接操作(参考 Task 6 落地)
def test_repo_sync_then_files_then_changes_then_push(client, repos_dir, tmp_path, db_session):
    ah = _admin_headers(client, db_session)
    from app.database import SessionLocal
    from app.models import Project
    db = SessionLocal()
    try:
        bare = _make_bare_origin(tmp_path)
        proj = Project(name="repo 路由项目", git_repo_url=f"file:///{bare.as_posix()}", git_token="tok")
        db.add(proj)
        db.commit()
        _seed_api_repo(db, proj)  # Task 2(方案 B):端点按 api 仓行解析
        # sync
        r = client.post(f"/api/projects/{proj.id}/repo/sync", json={}, headers=ah)
        assert r.status_code == 200
        assert r.json()["cloned"] is True or r.json()["updated"] is True
        # files
        r = client.get(f"/api/projects/{proj.id}/repo/files", headers=ah)
        assert r.status_code == 200
        assert "needs_sync" not in r.json()
        # file
        r = client.get(f"/api/projects/{proj.id}/repo/file", params={"path": "README.md"}, headers=ah)
        assert r.status_code == 200
        assert r.json()["content"] == "hi"
        assert r.json()["language"] == "markdown"
        # changes(无)
        r = client.get(f"/api/projects/{proj.id}/repo/changes", headers=ah)
        assert r.status_code == 200
        assert r.json()["files"] == []
        # branches
        r = client.get(f"/api/projects/{proj.id}/repo/branches", headers=ah)
        assert r.status_code == 200
        assert "main" in r.json()["branches"]
    finally:
        db.close()


def test_repo_files_needs_sync_when_absent(client, repos_dir, tmp_path, db_session):
    ah = _admin_headers(client, db_session)
    from app.database import SessionLocal
    from app.models import Project
    db = SessionLocal()
    try:
        bare = _make_bare_origin(tmp_path)
        proj = Project(name="未同步项目", git_repo_url=f"file:///{bare.as_posix()}", git_token="tok")
        db.add(proj)
        db.commit()
        _seed_api_repo(db, proj)  # Task 2(方案 B):files 按 api 仓行解析,行存在但未同步 → needs_sync
        r = client.get(f"/api/projects/{proj.id}/repo/files", headers=ah)
        assert r.status_code == 200
        assert r.json() == {"needs_sync": True}
    finally:
        db.close()


def test_repo_push_success(client, repos_dir, tmp_path, db_session):
    ah = _admin_headers(client, db_session)
    from app.database import SessionLocal
    from app.models import Project
    db = SessionLocal()
    try:
        bare = _make_bare_origin(tmp_path)
        proj = Project(name="推送项目", git_repo_url=f"file:///{bare.as_posix()}", git_token="tok")
        db.add(proj)
        db.commit()
        api_row = _seed_api_repo(db, proj)  # Task 2(方案 B):sync/push 按 api 仓行解析
        client.post(f"/api/projects/{proj.id}/repo/sync", json={}, headers=ah)
        # push 端点落在 api 行的工作副本目录(repo_{id}_api),测试写入同目录
        wc = git_service.working_copy_path(api_row)
        (wc / "T.java").write_text("class T{}", encoding="utf-8")
        r = client.post(f"/api/projects/{proj.id}/repo/push", json={"files": ["T.java"], "branch": "dev", "commit_message": "test push"}, headers=ah)
        assert r.status_code == 200
        assert r.json()["ok"] is True
    finally:
        db.close()
