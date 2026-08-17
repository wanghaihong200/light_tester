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


# Issue D: tests/conftest.py 无 db_session fixture,改用 SessionLocal() 直接操作(参考 Task 6 落地)
def test_repo_sync_then_files_then_changes_then_push(client, repos_dir, tmp_path):
    from app.database import SessionLocal
    from app.models import Project
    db = SessionLocal()
    try:
        bare = _make_bare_origin(tmp_path)
        proj = Project(name="repo 路由项目", git_repo_url=f"file:///{bare.as_posix()}", git_token="tok")
        db.add(proj)
        db.commit()
        # sync
        r = client.post(f"/api/projects/{proj.id}/repo/sync")
        assert r.status_code == 200
        assert r.json()["cloned"] is True or r.json()["updated"] is True
        # files
        r = client.get(f"/api/projects/{proj.id}/repo/files")
        assert r.status_code == 200
        assert "needs_sync" not in r.json()
        # file
        r = client.get(f"/api/projects/{proj.id}/repo/file", params={"path": "README.md"})
        assert r.status_code == 200
        assert r.json()["content"] == "hi"
        assert r.json()["language"] == "markdown"
        # changes(无)
        r = client.get(f"/api/projects/{proj.id}/repo/changes")
        assert r.status_code == 200
        assert r.json()["files"] == []
        # branches
        r = client.get(f"/api/projects/{proj.id}/repo/branches")
        assert r.status_code == 200
        assert "main" in r.json()["branches"]
    finally:
        db.close()


def test_repo_files_needs_sync_when_absent(client, repos_dir, tmp_path):
    from app.database import SessionLocal
    from app.models import Project
    db = SessionLocal()
    try:
        bare = _make_bare_origin(tmp_path)
        proj = Project(name="未同步项目", git_repo_url=f"file:///{bare.as_posix()}", git_token="tok")
        db.add(proj)
        db.commit()
        r = client.get(f"/api/projects/{proj.id}/repo/files")
        assert r.status_code == 200
        assert r.json() == {"needs_sync": True}
    finally:
        db.close()


def test_repo_push_success(client, repos_dir, tmp_path):
    from app.database import SessionLocal
    from app.models import Project
    db = SessionLocal()
    try:
        bare = _make_bare_origin(tmp_path)
        proj = Project(name="推送项目", git_repo_url=f"file:///{bare.as_posix()}", git_token="tok")
        db.add(proj)
        db.commit()
        client.post(f"/api/projects/{proj.id}/repo/sync")
        wc = git_service.working_copy_path(proj)
        (wc / "T.java").write_text("class T{}", encoding="utf-8")
        r = client.post(f"/api/projects/{proj.id}/repo/push", json={"files": ["T.java"], "branch": "dev", "commit_message": "test push"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
    finally:
        db.close()
