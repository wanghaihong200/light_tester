"""Task 12(计划 12):POST /api/app-scripts/{id}/export —— 翻译 SoloPi JSON 为 Appium pytest 产物并推送 kind=app 仓。

契约:成功 200 {...PushResult, files};翻译失败 400 {"detail": {"errors": [..]}};app 仓未配置 400(detail 含 app)。

对 brief 样例的仓内现状对齐(非行为偏离):
- _admin_headers 需带 db(Task 7 已提交签名 _admin_headers(client, db_session));
- 补 db 别名 fixture(conftest 提供的是 db_session,使测试体与 plan 稿一致);
- 补 autouse TRUNCATE automation_repos + app_scripts/app_runs 清理(conftest._TABLES 未含;
  形态照抄 tests/test_repo_multikind.py 与 tests/test_app_models.py 先例);
- 补 repos_dir fixture(monkeypatch settings.repos_dir → tmp):working copy 落 tmp,
  不污染仓库根 data/(同 tests/test_ui_script_export.py / tests/test_repo_multikind.py 先例)。"""

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app import git_service
from app.database import SessionLocal
from app.models import AutomationRepo, AppScript

from tests.test_app_scripts_api import _CASE, _admin_headers, _auth, _mk_project


@pytest.fixture()
def db(db_session):
    """conftest 提供的是 db_session;这里起别名,使测试体与 plan 稿一致。"""
    return db_session


@pytest.fixture(autouse=True)
def _clean_automation_repos():
    """conftest._TABLES 未包含 automation_repos;projects 被 TRUNCATE 复位自增后,
    残留行会撞 uq_autorepo_project_kind(test_repo_multikind 同款清理)。"""
    yield
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        session.execute(text("TRUNCATE TABLE automation_repos"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        session.commit()
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _clean_app_tables():
    """本文件会写 app_scripts 行;清理方式同 tests/test_app_models.py 先例。"""
    yield
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        session.execute(text("TRUNCATE TABLE app_runs"))
        session.execute(text("TRUNCATE TABLE app_scripts"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        session.commit()
    finally:
        session.close()


@pytest.fixture
def repos_dir(tmp_path, monkeypatch):
    """导出的 working copy 落到 tmp,不污染仓库根 data/(test_ui_script_export 同款)。"""
    d = tmp_path / "repos"
    d.mkdir()
    monkeypatch.setattr(git_service.settings, "repos_dir", d)
    return d


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


def _mk_script(db, pid) -> AppScript:
    s = AppScript(project_id=pid, name="下单冒烟", case_json=_CASE, app_package="com.example.shop")
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_export_pushes_to_app_repo(client, db, repos_dir, tmp_path):
    h = _admin_headers(client, db)
    pid = _mk_project(client, h, "导出app项目")
    bare = _make_bare_origin(tmp_path)
    db.add(AutomationRepo(project_id=pid, kind="app", repo_url=f"file:///{bare.as_posix()}"))
    db.commit()
    s = _mk_script(db, pid)
    r = client.post(f"/api/app-scripts/{s.id}/export", headers=h,
                    json={"branch": "main", "commit_message": "导出测试"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["branch"] == "main"
    assert any(f.startswith("test_") for f in body["files"])
    assert "RUN.md" in body["files"]


def test_export_without_repo_400(client, db):
    h = _admin_headers(client, db)
    pid = _mk_project(client, h, "无app仓项目")
    s = _mk_script(db, pid)
    r = client.post(f"/api/app-scripts/{s.id}/export", headers=h, json={"branch": "main"})
    assert r.status_code == 400
    assert "app" in r.json()["detail"]


def test_export_untranslatable_400(client, db, repos_dir, tmp_path):
    h = _admin_headers(client, db)
    pid = _mk_project(client, h, "拒导项目")
    bare = _make_bare_origin(tmp_path)
    db.add(AutomationRepo(project_id=pid, kind="app", repo_url=f"file:///{bare.as_posix()}"))
    db.commit()
    case = {
        "caseName": "含手势", "targetAppPackage": "com.a",
        "operationLog": {"steps": [
            {"operationNode": None,
             "operationMethod": {"actionEnum": "GESTURE",
                                 "operationParam": {"gesturePath": "1,1;2,2", "gestureFilter": "0.3"},
                                 "encrypt": False, "safeEncrypt": False},
             "operationIndex": 0, "operationId": "g", "stepId": "s1"}]}}
    s = AppScript(project_id=pid, name="含手势", case_json=case, app_package="com.a")
    db.add(s)
    db.commit()
    db.refresh(s)
    r = client.post(f"/api/app-scripts/{s.id}/export", headers=h, json={"branch": "main"})
    assert r.status_code == 400
    assert any("GESTURE" in e for e in r.json()["detail"]["errors"])


def test_export_viewer_403(client, db, make_user):
    """viewer 无导出权:推外部仓 = editor 闸 → 403(非成员才是 404)。
    模式照抄 tests/test_ui_script_export.py::test_export_viewer_403;建号/赋权走 app 域 _auth 同型 helper。"""
    h = _admin_headers(client, db)
    pid = _mk_project(client, h, "viewer导出app项目")
    s = _mk_script(db, pid)
    vh = _auth(client, db, make_user, "appexpviewer", project_ids=[pid], role="viewer")
    r = client.post(f"/api/app-scripts/{s.id}/export", headers=vh, json={"branch": "main"})
    assert r.status_code == 403


def test_export_non_member_404(client, db, make_user):
    """可见性先行:非项目成员对导出端点是 404(不泄漏存在性)。
    模式照抄 tests/test_ui_script_export.py::test_export_non_member_404。"""
    h = _admin_headers(client, db)
    pid = _mk_project(client, h, "外人导出app项目")
    s = _mk_script(db, pid)
    oh = _auth(client, db, make_user, "appexpoutsider", project_ids=[], role="editor")
    r = client.post(f"/api/app-scripts/{s.id}/export", headers=oh, json={"branch": "main"})
    assert r.status_code == 404
