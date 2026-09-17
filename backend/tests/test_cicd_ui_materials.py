# backend/tests/test_cicd_ui_materials.py
"""分支即事实源:GET /api/projects/{id}/ui-script-materials —— web 脚本导出文件在指定分支的存在性。

契约:200 [{script_id, name, file, exists}](file 与导出/触发校验同一条 slugify 规则);
未配 web 仓 400;分支不存在 400;非成员 404(可见性先行);viewer 可读。
helper 形态照抄 tests/test_ui_script_export.py(automation_repos 清理 + 裸仓制造)。
"""
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app.bootstrap import ensure_bootstrap_admin
from app.database import SessionLocal
from app.models import AutomationRepo, Project, ProjectMember, UiScript


@pytest.fixture(autouse=True)
def _clean_automation_repos():
    """conftest._TABLES 未包含 automation_repos;TRUNCATE 复位自增后残留行会撞唯一约束。"""
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


def _make_bare_origin(tmp_path: Path, main_files: list[str], dev_files: list[str]) -> Path:
    """裸仓:main 带 main_files;dev_files 非空时才建 dev 分支并**删掉 main 文件**再提交
    (否则 dev 继承 main 文件集,断言不了互斥;dev 无变更可提交时 commit 会报错)。"""
    work = tmp_path / "origin_work"
    work.mkdir()
    def _git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=work, check=True, capture_output=True)
    _git("init", "-q", "-b", "main")
    _git("config", "user.email", "t@t.com")
    _git("config", "user.name", "t")
    for f in main_files:
        (work / f).parent.mkdir(parents=True, exist_ok=True)
        (work / f).write_text("x", encoding="utf-8")
    _git("add", ".")
    _git("commit", "-qm", "init")
    if dev_files:
        _git("checkout", "-q", "-b", "dev")
        for f in main_files:
            (work / f).unlink(missing_ok=True)
        for f in dev_files:
            (work / f).parent.mkdir(parents=True, exist_ok=True)
            (work / f).write_text("x", encoding="utf-8")
        _git("add", "-A")
        _git("commit", "-qm", "dev")
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True, capture_output=True)
    return bare


def _admin_headers(client, db):
    ensure_bootstrap_admin(db)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_materials_flags_per_branch(client, db_session, repos_dir, tmp_path):
    p = Project(name="物料项目")
    db_session.add(p)
    db_session.commit()
    s1 = UiScript(project_id=p.id, name="login", script={"meta": {"target": "web"}})
    s2 = UiScript(project_id=p.id, name="other", script={"meta": {"target": "web"}})
    db_session.add_all([s1, s2])
    db_session.commit()
    f1, f2 = f"test_{s1.id}_login.py", f"test_{s2.id}_other.py"
    bare = _make_bare_origin(tmp_path, main_files=[f1], dev_files=[f2])
    db_session.add(AutomationRepo(project_id=p.id, kind="web", repo_url=f"file:///{bare.as_posix()}"))
    db_session.commit()
    h = _admin_headers(client, db_session)
    r = client.get(f"/api/projects/{p.id}/ui-script-materials", params={"branch": "main"}, headers=h)
    assert r.status_code == 200, r.text
    rows = {row["script_id"]: row for row in r.json()}
    assert rows[s1.id]["file"] == f1 and rows[s1.id]["exists"] is True
    assert rows[s2.id]["exists"] is False
    r = client.get(f"/api/projects/{p.id}/ui-script-materials", params={"branch": "dev"}, headers=h)
    rows = {row["script_id"]: row for row in r.json()}
    assert rows[s1.id]["exists"] is False and rows[s2.id]["exists"] is True


def test_materials_branch_missing_400(client, db_session, repos_dir, tmp_path):
    p = Project(name="分支缺失项目")
    db_session.add(p)
    db_session.commit()
    db_session.add(UiScript(project_id=p.id, name="login", script={"meta": {"target": "web"}}))
    db_session.commit()
    bare = _make_bare_origin(tmp_path, main_files=["README.md"], dev_files=[])
    db_session.add(AutomationRepo(project_id=p.id, kind="web", repo_url=f"file:///{bare.as_posix()}"))
    db_session.commit()
    h = _admin_headers(client, db_session)
    assert client.get(f"/api/projects/{p.id}/ui-script-materials",
                      params={"branch": "nope"}, headers=h).status_code == 400


def test_materials_without_web_repo_400(client, db_session, make_user):
    p = Project(name="无仓项目")
    db_session.add(p)
    db_session.commit()
    u = make_user(db_session, "matviewer")
    db_session.add(ProjectMember(project_id=p.id, user_id=u.id, role="viewer"))
    db_session.commit()
    tok = client.post("/api/auth/login", json={"username": "matviewer", "password": "pw-matviewer"}).json()["token"]
    r = client.get(f"/api/projects/{p.id}/ui-script-materials", params={"branch": "main"},
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400 and "web" in r.json()["detail"]


def test_materials_non_member_404(client, db_session, repos_dir, tmp_path, make_user):
    p = Project(name="孤岛项目")
    db_session.add(p)
    db_session.commit()
    bare = _make_bare_origin(tmp_path, main_files=["README.md"], dev_files=[])
    db_session.add(AutomationRepo(project_id=p.id, kind="web", repo_url=f"file:///{bare.as_posix()}"))
    db_session.commit()
    u = make_user(db_session, "outsider2")
    db_session.commit()
    tok = client.post("/api/auth/login", json={"username": "outsider2", "password": "pw-outsider2"}).json()["token"]
    r = client.get(f"/api/projects/{p.id}/ui-script-materials", params={"branch": "main"},
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404
