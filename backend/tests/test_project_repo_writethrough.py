# backend/tests/test_project_repo_writethrough.py
"""计划 11 Task 3:项目 git 字段写透 AutomationRepo(kind=api) + jobs api_generation 切 api 仓解析。

方案 B(用户拍板,严格存储模型):git_repo_url/git_token 唯一事实源是 AutomationRepo 行,
Project 两个旧列停写保留,任何读取不回退旧列。"""
import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.models import AutomationRepo, Document, Module, Project


@pytest.fixture()
def db(db_session):
    """conftest 提供的是 db_session;这里起别名,使测试体与 plan 稿一致。"""
    return db_session


@pytest.fixture(autouse=True)
def _clean_automation_repos():
    """conftest._TABLES 未包含 automation_repos(且不许改 conftest)。

    与 tests/test_repo_multikind.py 同款清理,额外在**测试前**也清一次:
    本文件按字母序跑在 test_project_isolation.py 之后,后者经 create_project
    留下 api 仓行,projects 被 TRUNCATE 复位自增后 id 复用,残留行会让
    「无 git 字段建项目 → 无 api 仓行」断言误命中。"""
    def _truncate():
        session = SessionLocal()
        try:
            session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
            session.execute(text("TRUNCATE TABLE automation_repos"))
            session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
            session.commit()
        finally:
            session.close()

    _truncate()
    yield
    _truncate()


def _h(client, db_session):
    """admin 登录头(admin 直通所有项目)。plan 稿猜想的
    tests.test_auth_api.login_headers 并不存在,按 test_repo_multikind.py
    的 bootstrap-admin 既有模式拿 token。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _mk_document(db, project):
    """照抄 tests/test_job_pipeline.py::_seed 的直插建文档方式(校验只查行,不读文件)。
    flush 不 commit——由调用方在打 API 前统一 commit(与 _seed 相同)。"""
    d = Document(project_id=project.id, filename="需求.md", storage_path="/tmp/fake.md")
    db.add(d)
    db.flush()
    return d


def _mk_module(db, project):
    m = Module(project_id=project.id, name="接口模块")
    db.add(m)
    db.flush()
    return m


def test_create_project_writes_api_repo(client, db):
    h = _h(client, db)
    r = client.post("/api/projects", headers=h,
                    json={"name": "写透项目", "git_repo_url": "file:///tmp/api-repo", "git_token": "tk"})
    assert r.status_code in (200, 201)
    pid = r.json()["id"]
    db.commit()  # MySQL REPEATABLE_READ:结束本会话旧快照,才能读到 API 会话写入的行
    row = db.query(AutomationRepo).filter_by(project_id=pid, kind="api", is_deleted=False).first()
    assert row is not None
    assert row.repo_url == "file:///tmp/api-repo"
    assert row.repo_token == "tk"
    # ProjectOut 回读:git_repo_url 来自 api 仓行
    r2 = client.get(f"/api/projects/{pid}", headers=h)
    assert r2.json()["git_repo_url"] == "file:///tmp/api-repo"
    # 列表口径同样来自 api 仓行(前端零改动)
    lst = client.get("/api/projects", headers=h).json()
    assert [p["git_repo_url"] for p in lst if p["id"] == pid] == ["file:///tmp/api-repo"]
    # Project 旧列停写(列保留,不再落值)
    db.commit()
    legacy = db.get(Project, pid)
    assert legacy.git_repo_url is None and legacy.git_token is None


def test_create_project_without_git_fields_no_repo_row(client, db):
    """不传 git 字段建项目:不产生 api 仓行(无仓生成项目靠它拿到 400)。"""
    h = _h(client, db)
    pid = client.post("/api/projects", headers=h, json={"name": "无仓项目"}).json()["id"]
    db.commit()  # 刷新快照,确认 API 会话确实没写 api 仓行
    assert db.query(AutomationRepo).filter_by(project_id=pid, kind="api").first() is None
    assert client.get(f"/api/projects/{pid}", headers=h).json()["git_repo_url"] is None


def test_update_project_clears_api_repo(client, db):
    h = _h(client, db)
    r = client.post("/api/projects", headers=h,
                    json={"name": "清空项目", "git_repo_url": "file:///tmp/a", "git_token": "tk"})
    pid = r.json()["id"]
    r2 = client.put(f"/api/projects/{pid}", headers=h,
                    json={"name": "清空项目", "git_repo_url": "", "git_token": ""})
    assert r2.status_code == 200
    db.commit()  # 刷新快照
    row = db.query(AutomationRepo).filter_by(project_id=pid, kind="api", is_deleted=False).first()
    assert row.repo_url == ""
    # 回读:详情吐的是 api 仓行的清空值(与旧行为「旧列存 ""」对外表现一致)
    assert client.get(f"/api/projects/{pid}", headers=h).json()["git_repo_url"] == ""


def test_update_project_keeps_token_when_field_absent(client, db):
    """exclude_unset 语义:payload 未出现的字段保留原值(前端编辑框只回传改动的字段)。"""
    h = _h(client, db)
    pid = client.post(
        "/api/projects", headers=h,
        json={"name": "保token项目", "git_repo_url": "http://a/r.git", "git_token": "tk1"},
    ).json()["id"]
    r = client.put(f"/api/projects/{pid}", headers=h,
                   json={"name": "保token项目", "git_repo_url": "http://b/r.git"})
    assert r.status_code == 200
    db.commit()  # 刷新快照
    row = db.query(AutomationRepo).filter_by(project_id=pid, kind="api", is_deleted=False).first()
    assert row.repo_url == "http://b/r.git"
    assert row.repo_token == "tk1"
    assert db.get(Project, pid).git_token is None  # 旧列依旧停写


def test_delete_project_with_api_repo_row_ok(client, db):
    """写透后项目删除不得被 automation_repos 外键挡住(1451):删项目需先清其仓行。"""
    h = _h(client, db)
    pid = client.post("/api/projects", headers=h,
                      json={"name": "带仓删除项目", "git_repo_url": "file:///tmp/x", "git_token": "tk"}).json()["id"]
    assert client.delete(f"/api/projects/{pid}", headers=h).status_code == 204
    db.commit()  # 刷新快照
    assert db.query(AutomationRepo).filter_by(project_id=pid).count() == 0


def test_jobs_api_gen_requires_api_repo(client, db):
    """api_generation 无 api 仓行 → 400(不再读 Project 旧列)。"""
    h = _h(client, db)
    p = Project(name="无仓生成项目")
    db.add(p); db.commit(); db.refresh(p)
    doc = _mk_document(db, p)
    mod = _mk_module(db, p)
    db.commit()  # 直插行落库,API 会话才可见(照抄 test_job_dispatch 的直插+commit 顺序)
    # 字段名以 jobs.JobCreate 现状为准:job_type / document_id / target_module_id
    r = client.post(f"/api/projects/{p.id}/jobs", headers=h,
                    json={"job_type": "api_generation", "document_id": doc.id, "target_module_id": mod.id})
    assert r.status_code == 400
    assert "接口自动化仓" in r.json()["detail"]


def test_jobs_api_gen_ignores_project_legacy_columns(client, db):
    """方案 B 严格存储:只种 Project 旧列(绕过 API 的历史数据)→ 仍 400,不回退旧列。"""
    h = _h(client, db)
    p = Project(name="仅旧列项目", git_repo_url="http://legacy/repo.git", git_token="tk")
    db.add(p); db.commit(); db.refresh(p)
    doc = _mk_document(db, p)
    mod = _mk_module(db, p)
    db.commit()
    r = client.post(f"/api/projects/{p.id}/jobs", headers=h,
                    json={"job_type": "api_generation", "document_id": doc.id, "target_module_id": mod.id})
    assert r.status_code == 400
    assert "接口自动化仓" in r.json()["detail"]


def test_jobs_api_gen_reads_api_repo_row(client, db):
    """写透产生的 api 仓行使 api_generation 校验通过;file:// 属仓配置合法值但
    生成入口强制 http(s) → 无效 URL 报 400 新文案。"""
    h = _h(client, db)
    pid = client.post(
        "/api/projects", headers=h,
        json={"name": "行仓生成项目", "git_repo_url": "file:///tmp/local", "git_token": "tk"},
    ).json()["id"]
    db.commit()  # 刷新快照后才能在 db 会话里看到 API 会话建的项目
    p = db.get(Project, pid)
    doc = _mk_document(db, p)
    mod = _mk_module(db, p)
    db.commit()
    r = client.post(f"/api/projects/{pid}/jobs", headers=h,
                    json={"job_type": "api_generation", "document_id": doc.id, "target_module_id": mod.id})
    assert r.status_code == 400
    assert "http(s)" in r.json()["detail"]
    # 换成 http(s) 仓 → 校验放行(201)
    client.put(f"/api/projects/{pid}", headers=h, json={"git_repo_url": "http://gitlab.example/r.git"})
    r2 = client.post(f"/api/projects/{pid}/jobs", headers=h,
                     json={"job_type": "api_generation", "document_id": doc.id, "target_module_id": mod.id})
    assert r2.status_code == 201
