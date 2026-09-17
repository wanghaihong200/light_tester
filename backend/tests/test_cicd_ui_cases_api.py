# backend/tests/test_cicd_ui_cases_api.py
"""计划 17 Task 4:Web用例注册表端点(scan/list)+ interface-cases 域过滤。

契约:POST /ui-cases/scan {branch} → 统计四元组;GET /ui-cases?branch= 仅 web 行;
interface-cases 仅 api 行(web 行不污染);未配 web 仓 400;分支不存在 400;viewer 不可扫描、
非成员 404。裸仓 fixture 照抄 tests/test_cicd_ui_materials.py。
"""
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app.bootstrap import ensure_bootstrap_admin
from app.database import SessionLocal
from app.models import AutomationRepo, Project, ProjectMember

SMOKE = '''import pytest

@pytest.mark.account("standard")
def test_login(page):
    """登录态直达。"""
    page.goto("/")
'''


@pytest.fixture(autouse=True)
def _clean_automation_repos():
    yield
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        session.execute(text("TRUNCATE TABLE automation_repos"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        session.commit()
    finally:
        session.close()


@pytest.fixture
def repos_dir(tmp_path, monkeypatch):
    d = tmp_path / "repos"
    d.mkdir()
    monkeypatch.setattr("app.git_service.settings.repos_dir", d)
    return d


def _make_pytest_origin(tmp_path: Path, files: dict[str, str]) -> Path:
    work = tmp_path / "origin_work"
    work.mkdir()

    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=work, check=True, capture_output=True)

    _git("init", "-q", "-b", "main")
    _git("config", "user.email", "t@t.com")
    _git("config", "user.name", "t")
    for rel, code in files.items():
        (work / rel).parent.mkdir(parents=True, exist_ok=True)
        (work / rel).write_text(code, encoding="utf-8")
    _git("add", ".")
    _git("commit", "-qm", "init")
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)],
                   check=True, capture_output=True)
    return bare


def _admin_headers(client, db):
    ensure_bootstrap_admin(db)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_scan_and_list_ui_cases(client, db_session, repos_dir, tmp_path):
    p = Project(name="web注册表")
    db_session.add(p)
    db_session.commit()
    bare = _make_pytest_origin(tmp_path, {"tests/test_smoke.py": SMOKE,
                                          "test_1_root.py": "def test_root():\n    pass\n"})
    db_session.add(AutomationRepo(project_id=p.id, kind="web", repo_url=f"file:///{bare.as_posix()}"))
    db_session.commit()
    h = _admin_headers(client, db_session)
    r = client.post(f"/api/projects/{p.id}/ui-cases/scan", json={"branch": "main"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"total": 2, "active": 2, "stale": 0, "added": 2}
    r = client.get(f"/api/projects/{p.id}/ui-cases", params={"branch": "main"}, headers=h)
    rows = {row["class_name"]: row for row in r.json()}
    assert set(rows) == {"tests/test_smoke.py", "test_1_root.py"}
    assert rows["tests/test_smoke.py"]["method"] == "test_login"
    assert rows["tests/test_smoke.py"]["title"] == "登录态直达。"
    assert rows["tests/test_smoke.py"]["markers"] == ["account:standard"]
    assert rows["tests/test_smoke.py"]["case_type"] == "web"
    # interface-cases 列表不被 web 行污染
    r = client.get(f"/api/projects/{p.id}/interface-cases", params={"branch": "main"}, headers=h)
    assert r.json() == []


def test_ui_cases_branch_missing_400(client, db_session, repos_dir, tmp_path):
    p = Project(name="分支缺失")
    db_session.add(p)
    db_session.commit()
    bare = _make_pytest_origin(tmp_path, {"README.md": "x"})
    db_session.add(AutomationRepo(project_id=p.id, kind="web", repo_url=f"file:///{bare.as_posix()}"))
    db_session.commit()
    h = _admin_headers(client, db_session)
    r = client.post(f"/api/projects/{p.id}/ui-cases/scan", json={"branch": "nope"}, headers=h)
    assert r.status_code == 400 and "同步失败" in r.json()["detail"]


def test_ui_scan_without_web_repo_400(client, db_session, make_user):
    p = Project(name="无web仓")
    db_session.add(p)
    db_session.commit()
    u = make_user(db_session, "uicase1")
    db_session.add(ProjectMember(project_id=p.id, user_id=u.id, role="editor"))
    db_session.commit()
    tok = client.post("/api/auth/login", json={"username": "uicase1", "password": "pw-uicase1"}).json()["token"]
    r = client.post(f"/api/projects/{p.id}/ui-cases/scan", json={"branch": "main"},
                    headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400 and "web" in r.json()["detail"]


def test_ui_scan_requires_editor_and_member(client, db_session, repos_dir, tmp_path, make_user):
    p = Project(name="权限")
    db_session.add(p)
    db_session.commit()
    bare = _make_pytest_origin(tmp_path, {"README.md": "x"})
    db_session.add(AutomationRepo(project_id=p.id, kind="web", repo_url=f"file:///{bare.as_posix()}"))
    u = make_user(db_session, "uicasev")
    db_session.add(ProjectMember(project_id=p.id, user_id=u.id, role="viewer"))
    db_session.commit()
    tok = client.post("/api/auth/login", json={"username": "uicasev", "password": "pw-uicasev"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.post(f"/api/projects/{p.id}/ui-cases/scan", json={"branch": "main"},
                       headers=h).status_code == 403
    # 非成员 404(可见性先行)
    ou = make_user(db_session, "uicaseout")
    db_session.commit()
    otok = client.post("/api/auth/login", json={"username": "uicaseout", "password": "pw-uicaseout"}).json()["token"]
    assert client.get(f"/api/projects/{p.id}/ui-cases", params={"branch": "main"},
                      headers={"Authorization": f"Bearer {otok}"}).status_code == 404
