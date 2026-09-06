# backend/tests/test_ui_script_export.py
"""计划 11 Task 6:POST /api/ui-scripts/{id}/export —— 导出 Playwright 产物并推送 web 仓。

契约:成功 200 {..PushResult, files};校验失败 400 {"detail": {"errors": [..]}}(ai 步/登录态缺失);
仓未配置 400(detail 含 web);非 web 端 400;viewer 403(editor 闸);非成员 404(可见性先行)。
helper 形态照抄 tests/test_repo_multikind.py(db 别名 + automation_repos 清理 + 裸仓制造)。
"""
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text

from app import git_service
from app.database import SessionLocal
from app.git_service import working_copy_path
from app.models import AutomationRepo, Project, ProjectMember, UiAuthState, UiScript


@pytest.fixture()
def db(db_session):
    """conftest 提供的是 db_session;起别名使测试体与 plan 稿一致。"""
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


@pytest.fixture
def repos_dir(tmp_path, monkeypatch):
    """导出的 working copy 落到 tmp,不污染仓库内 data/repos。"""
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


def _admin_headers(client, db):
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _viewer_headers(client, db, make_user, project_id, name="expviewer"):
    """viewer 成员(仅可读)——导出推外部仓须 editor,应 403。"""
    u = make_user(db, name)
    db.add(ProjectMember(project_id=project_id, user_id=u.id, role="viewer"))
    db.commit()
    tok = client.post("/api/auth/login", json={"username": name, "password": f"pw-{name}"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _mk_web_script(db, project_id, doc, name="导出脚本"):
    s = UiScript(project_id=project_id, name=name, script=doc)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


DOC = {
    "version": 1,
    "meta": {"target": "web"},
    "variables": [{"name": "user", "default": "bob"}],
    "steps": [{"id": 1, "action": "goto", "params": {"url": "https://x.example"}}],
}


def _mk_project_with_web_repo(db, tmp_path, name):
    p = Project(name=name)
    db.add(p)
    db.commit()
    db.refresh(p)
    bare = _make_bare_origin(tmp_path)
    db.add(AutomationRepo(project_id=p.id, kind="web", repo_url=f"file:///{bare.as_posix()}"))
    db.commit()
    return p, bare


def test_export_pushes_to_web_repo(client, db, repos_dir, tmp_path):
    p, bare = _mk_project_with_web_repo(db, tmp_path, "导出推送项目")
    s = _mk_web_script(db, p.id, DOC)
    h = _admin_headers(client, db)
    r = client.post(f"/api/ui-scripts/{s.id}/export", headers=h,
                    json={"branch": "main", "commit_message": "导出测试"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["branch"] == "main"
    assert any(f.startswith("test_") for f in body["files"])
    assert "RUN.md" in body["files"]
    # 端到端实证:文件先落 working copy 再 push,远程裸仓真的收到了产物
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"],
                         cwd=bare, capture_output=True, text=True, check=True).stdout
    lines = out.splitlines()
    assert any(ln.startswith("test_") and ln.endswith(".py") for ln in lines)
    assert "RUN.md" in lines
    # working copy 内的产物内容可读(非空壳)
    repo_row = db.query(AutomationRepo).filter_by(project_id=p.id, kind="web").first()
    wc = working_copy_path(repo_row)
    assert "page.goto" in (wc / next(f for f in body["files"] if f.startswith("test_"))).read_text(encoding="utf-8")


def test_export_without_web_repo_400(client, db):
    p = Project(name="无web仓导出项目")
    db.add(p)
    db.commit()
    db.refresh(p)
    s = _mk_web_script(db, p.id, DOC)
    h = _admin_headers(client, db)
    r = client.post(f"/api/ui-scripts/{s.id}/export", headers=h, json={"branch": "main"})
    assert r.status_code == 400
    assert "web" in r.json()["detail"]


def test_export_ai_step_400_with_errors(client, db, repos_dir, tmp_path):
    # 400 在推送前抛出,裸仓仅占位(repos_dir 已隔离,不会真推送)
    p, _bare = _mk_project_with_web_repo(db, tmp_path, "ai导出项目")
    doc = {"version": 2, "meta": {"target": "web"},
           "steps": [{"id": 1, "action": "ai_tap", "params": {"target": "按钮"}}]}
    s = _mk_web_script(db, p.id, doc)
    h = _admin_headers(client, db)
    r = client.post(f"/api/ui-scripts/{s.id}/export", headers=h, json={"branch": "main"})
    assert r.status_code == 400
    errors = r.json()["detail"]["errors"]
    assert isinstance(errors, list)
    assert any("ai_tap" in e for e in errors)


def test_export_android_target_400(client, db):
    p = Project(name="安卓导出项目")
    db.add(p)
    db.commit()
    db.refresh(p)
    doc = dict(DOC, meta={"target": "android"})
    s = _mk_web_script(db, p.id, doc)
    h = _admin_headers(client, db)
    r = client.post(f"/api/ui-scripts/{s.id}/export", headers=h, json={"branch": "main"})
    assert r.status_code == 400
    assert "web" in r.json()["detail"]


def test_export_viewer_403(client, db, make_user):
    """viewer 无导出权:推外部仓 = editor 闸 → 403(非成员才是 404)。"""
    p = Project(name="viewer导出项目")
    db.add(p)
    db.commit()
    db.refresh(p)
    s = _mk_web_script(db, p.id, DOC)
    vh = _viewer_headers(client, db, make_user, p.id)
    r = client.post(f"/api/ui-scripts/{s.id}/export", headers=vh, json={"branch": "main"})
    assert r.status_code == 403


def test_export_non_member_404(client, db, make_user):
    """可见性先行:非项目成员对导出端点是 404(不泄漏存在性)。"""
    p = Project(name="外人导出项目")
    db.add(p)
    db.commit()
    db.refresh(p)
    s = _mk_web_script(db, p.id, DOC)
    u = make_user(db, "expoutsider")
    db.commit()
    tok = client.post("/api/auth/login", json={"username": u.username, "password": "pw-expoutsider"}).json()["token"]
    r = client.post(f"/api/ui-scripts/{s.id}/export",
                    headers={"Authorization": f"Bearer {tok}"}, json={"branch": "main"})
    assert r.status_code == 404


def test_export_with_auth_state_attaches_storage_and_fixture(client, db, repos_dir, tmp_path):
    """meta.auth_state_id:storage_state 文件进 auth_states/,主测试文件注入 browser_context_args,RUN.md 无占位残留。"""
    import ast

    p, bare = _mk_project_with_web_repo(db, tmp_path, "登录态导出项目")
    state_file = tmp_path / "auth" / "admin_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    auth = UiAuthState(project_id=p.id, name="admin_state", storage_path=str(state_file))
    db.add(auth)
    db.commit()
    db.refresh(auth)
    doc = dict(DOC, meta={"target": "web", "auth_state_id": auth.id})
    s = _mk_web_script(db, p.id, doc)
    h = _admin_headers(client, db)
    r = client.post(f"/api/ui-scripts/{s.id}/export", headers=h,
                    json={"branch": "main", "commit_message": "带登录态导出"})
    assert r.status_code == 200, r.text
    body = r.json()
    rel = "auth_states/admin_state.json"
    assert rel in body["files"]
    repo_row = db.query(AutomationRepo).filter_by(project_id=p.id, kind="web").first()
    wc = working_copy_path(repo_row)
    # 仓内文件真实存在且内容即 storage_state
    assert (wc / rel).exists()
    assert (wc / rel).read_text(encoding="utf-8") == '{"cookies": [], "origins": []}'
    main_py = next(f for f in body["files"] if f.startswith("test_"))
    code = (wc / main_py).read_text(encoding="utf-8")
    assert "browser_context_args" in code and "storage_state" in code and "from pathlib import Path" in code
    assert "import pytest" in code
    ast.parse(code)  # 注入后仍是合法 Python
    run_md = (wc / "RUN.md").read_text(encoding="utf-8")
    assert "{auth_section}" not in run_md and "{auth_note}" not in run_md
    assert rel in run_md  # 登录态说明已拼进 RUN.md
    # 远程裸仓也收到 auth_states 文件
    out = subprocess.run(["git", "ls-tree", "-r", "--name-only", "main"],
                         cwd=bare, capture_output=True, text=True, check=True).stdout
    assert rel in out.splitlines()


def test_export_auth_state_deleted_400(client, db, repos_dir, tmp_path):
    """登录态行已删/不存在 → 400 errors 提示登录态不存在(不产文件不推送)。"""
    p, _bare = _mk_project_with_web_repo(db, tmp_path, "登录态缺失导出项目")
    doc = dict(DOC, meta={"target": "web", "auth_state_id": 999999})
    s = _mk_web_script(db, p.id, doc)
    h = _admin_headers(client, db)
    r = client.post(f"/api/ui-scripts/{s.id}/export", headers=h, json={"branch": "main"})
    assert r.status_code == 400
    errors = r.json()["detail"]["errors"]
    assert any("登录态" in e and "不存在" in e for e in errors)


def test_export_auth_state_file_missing_400(client, db, repos_dir, tmp_path):
    """登录态行在但 storage 文件丢失 → 400 errors 提示文件缺失。"""
    p, _bare = _mk_project_with_web_repo(db, tmp_path, "登录态丢文件导出项目")
    auth = UiAuthState(project_id=p.id, name="ghost_state",
                       storage_path=str(tmp_path / "auth" / "gone.json"))
    db.add(auth)
    db.commit()
    db.refresh(auth)
    doc = dict(DOC, meta={"target": "web", "auth_state_id": auth.id})
    s = _mk_web_script(db, p.id, doc)
    h = _admin_headers(client, db)
    r = client.post(f"/api/ui-scripts/{s.id}/export", headers=h, json={"branch": "main"})
    assert r.status_code == 400
    errors = r.json()["detail"]["errors"]
    assert any("缺失" in e and "ghost_state" in e for e in errors)


def test_export_auth_state_name_traversal_400(client, db, repos_dir, tmp_path):
    """登录态名含 ../ 路径穿越 → 400 errors(越界文案);写盘守卫生效,wc 外不得落任何文件。"""
    p, _bare = _mk_project_with_web_repo(db, tmp_path, "越界名导出项目")
    state_file = tmp_path / "auth" / "state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text('{"cookies": []}', encoding="utf-8")
    auth = UiAuthState(project_id=p.id, name="../../evil", storage_path=str(state_file))
    db.add(auth)
    db.commit()
    db.refresh(auth)
    doc = dict(DOC, meta={"target": "web", "auth_state_id": auth.id})
    s = _mk_web_script(db, p.id, doc)
    h = _admin_headers(client, db)
    r = client.post(f"/api/ui-scripts/{s.id}/export", headers=h, json={"branch": "main"})
    assert r.status_code == 400
    errors = r.json()["detail"]["errors"]
    assert errors and any("越界" in e for e in errors)
    # 写穿断言:repos_dir 下除 web 仓 working copy 目录本身,不得出现任何新文件
    repo_row = db.query(AutomationRepo).filter_by(project_id=p.id, kind="web").first()
    assert sorted(x.name for x in repos_dir.iterdir()) == [working_copy_path(repo_row).name]
    assert not (repos_dir / "evil.json").exists()
