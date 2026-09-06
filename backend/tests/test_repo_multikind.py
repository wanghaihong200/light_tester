# backend/tests/test_repo_multikind.py
"""计划 11 Task 2:git_service 多仓适配 + repo 路由 kind 参数 + 仓配置 API。"""
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app import git_service
from app.database import SessionLocal
from app.git_service import working_copy_path
from app.models import AutomationRepo, Project


@pytest.fixture()
def db(db_session):
    """conftest 提供的是 db_session;这里起别名,使测试体与 plan 稿一致。"""
    return db_session


@pytest.fixture(autouse=True)
def _clean_automation_repos():
    """conftest._TABLES 未包含 automation_repos;若不清理,projects 被 TRUNCATE
    复位自增后 id 复用,残留行会撞 uq_autorepo_project_kind。"""
    yield
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        session.execute(text("TRUNCATE TABLE automation_repos"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        session.commit()
    finally:
        session.close()


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


def test_working_copy_path_kind_aware():
    p = Project(id=7, name="p")
    r = AutomationRepo(id=9, project_id=7, kind="web", repo_url="file:///x")
    assert working_copy_path(p).name == "repo_7"
    assert working_copy_path(r).name == "repo_7_web"


def test_git_flow_via_web_repo(repos_dir, tmp_path):
    """AutomationRepo 直接过 git_service 全链路:sync→写文件→push。"""
    bare = _make_bare_origin(tmp_path)
    repo = AutomationRepo(project_id=1, kind="web", repo_url=f"file:///{bare.as_posix()}", repo_token=None)
    git_service.sync_repo(repo)
    wc = working_copy_path(repo)
    (wc / "test_demo.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    r = git_service.push_files(repo, ["test_demo.py"], "main", "导出测试")
    assert r.ok is True
    assert "test_demo.py" in r.pushed_files


def _auth_headers(client, db_session):
    """tests 里无现成 login_headers helper;按 test_repo_router.py/_admin_headers 现状拿 admin token。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_repo_endpoints_kind_param(client, db):
    import tempfile

    p = Project(name="多仓路由项目")
    db.add(p); db.commit(); db.refresh(p)
    tmp = Path(tempfile.mkdtemp())
    # 造 web 裸仓
    work = tmp / "w"; work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=work, check=True)
    (work / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=work, check=True)
    bare = tmp / "w.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
    db.add(AutomationRepo(project_id=p.id, kind="web", repo_url=f"file:///{bare.as_posix()}"))
    db.commit()

    h = _auth_headers(client, db)
    # 先同步 web 仓(plan 稿缺此步:行存在但未同步时 files 返回 needs_sync)
    rs = client.post(f"/api/projects/{p.id}/repo/sync?kind=web", json={}, headers=h)
    assert rs.status_code == 200
    assert rs.json()["cloned"] is True or rs.json()["updated"] is True
    # kind=web 走 web 仓(files 直接返回 FileNode,顶层即 name/is_dir)
    resp = client.get(f"/api/projects/{p.id}/repo/files?kind=web", headers=h)
    assert resp.status_code == 200
    assert resp.json()["name"] == "w" or resp.json()["is_dir"] is True
    # kind 未配置 → files 是 200 needs_config(计划正文:不是 400)
    resp2 = client.get(f"/api/projects/{p.id}/repo/files?kind=app", headers=h)
    assert resp2.status_code == 200
    assert resp2.json() == {"needs_config": True}
    # kind 未配置 → 写端点 require_repo 400,detail 含 kind 名
    resp2b = client.post(f"/api/projects/{p.id}/repo/sync?kind=app", json={}, headers=h)
    assert resp2b.status_code == 400
    assert "app" in resp2b.json()["detail"]
    # 非法 kind → 400
    resp3 = client.get(f"/api/projects/{p.id}/repo/files?kind=hack", headers=h)
    assert resp3.status_code == 400


def test_automation_repo_config_api(client, db):
    p = Project(name="仓配置项目")
    db.add(p); db.commit(); db.refresh(p)
    h = _auth_headers(client, db)
    # PUT upsert(挂在既有 router prefix 下:…/repo/automation-repos,与 Task 8 前端一致)
    r = client.put(f"/api/projects/{p.id}/repo/automation-repos/web",
                   headers=h, json={"repo_url": "file:///tmp/webx", "repo_token": ""})
    assert r.status_code == 200
    assert r.json()["kind"] == "web"
    # GET 列表含 web 行
    r2 = client.get(f"/api/projects/{p.id}/repo/automation-repos", headers=h)
    kinds = {row["kind"] for row in r2.json()}
    assert kinds == {"web"}
    # 非法 kind 404/400
    r3 = client.put(f"/api/projects/{p.id}/repo/automation-repos/hack",
                    headers=h, json={"repo_url": "file:///x"})
    assert r3.status_code in (400, 404)
    # 非法 URL 400
    r4 = client.put(f"/api/projects/{p.id}/repo/automation-repos/web",
                    headers=h, json={"repo_url": "ftp://bad"})
    assert r4.status_code == 400
