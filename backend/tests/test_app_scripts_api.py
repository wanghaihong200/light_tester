"""Task 7(计划 12):app_scripts CRUD 路由 API 测试(SoloPi 原生 JSON 校验接线/高危确认门/软删/viewer 403)。

对 brief 样例的仓内现状对齐(非行为偏离):
- 登录响应字段是 token 不是 access_token(app/routers/auth.py:LoginOut(token=…),计划稿笔误);
- admin 登录前须 ensure_bootstrap_admin(db_session)(先例 tests/test_jobs_repo_isolation.py 的 _admin_headers);
- viewer 建号/赋权照抄 tests/test_jobs_repo_isolation.py 的 _auth 同型 helper(建号密码 pw-<name>,
  授权走 ProjectMember(project_id, user_id, role));brief 里 make_viewer_headers 不存在,断言点不变(viewer 写 → 403);
- 补 db 别名 fixture + autouse TRUNCATE app_scripts 清理(conftest._TABLES 未含,同 tests/test_app_models.py)。"""

import pytest
from sqlalchemy import text

from app.database import SessionLocal


@pytest.fixture()
def db(db_session):
    """conftest 提供的是 db_session;这里起别名,使测试体与 plan 稿一致。"""
    return db_session


@pytest.fixture(autouse=True)
def _clean_app_tables():
    """本文件会写 app_scripts 行;conftest._TABLES 未含该表,projects 被 TRUNCATE 复位自增后
    id 复用,残留行会串项目污染全量回归(清理方式同 tests/test_app_models.py)。"""
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


def _admin_headers(client, db_session):
    """bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    """建用户+分配项目+登录,返回 Authorization 头。(复制自 tests/test_jobs_repo_isolation.py 同型)"""
    u = make_user(db_session, name)
    from app.models import Project, ProjectMember

    if project_ids is None:
        pids: list[int] = []
    elif isinstance(project_ids, (list, tuple)):
        pids = list(project_ids)
    else:
        pids = [project_ids]
    for pid in pids:
        if db_session.get(Project, pid) is None:
            db_session.add(Project(name=f"p-{pid}"))
            db_session.flush()
        db_session.add(ProjectMember(project_id=pid, user_id=u.id, role=role))
    db_session.commit()
    r = client.post("/api/auth/login", json={"username": name, "password": f"pw-{name}"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


_CASE = {
    "caseName": "下单冒烟", "targetAppPackage": "com.example.shop",
    "operationLog": {"steps": [
        {"operationNode": None,
         "operationMethod": {"actionEnum": "SLEEP", "operationParam": {"text": "500"},
                             "encrypt": False, "safeEncrypt": False},
         "operationIndex": 0, "operationId": "g1", "stepId": "s1"}]}}


def _mk_project(client, headers, name="app脚本项目") -> int:
    r = client.post("/api/projects", headers=headers, json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["id"]


def test_create_defaults_name_to_case_name(client, db):
    h = _admin_headers(client, db)
    pid = _mk_project(client, h)
    r = client.post(f"/api/projects/{pid}/app-scripts", headers=h,
                    json={"case": _CASE})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "下单冒烟"
    assert body["app_package"] == "com.example.shop"
    assert body["case_json"]["caseName"] == "下单冒烟"


def test_create_invalid_case_400(client, db):
    h = _admin_headers(client, db)
    pid = _mk_project(client, h, "invalid-case项目")
    bad = {"caseName": "", "targetAppPackage": "com.a", "operationLog": {"steps": []}}
    r = client.post(f"/api/projects/{pid}/app-scripts", headers=h, json={"case": bad})
    assert r.status_code == 400
    assert "不合法" in r.json()["detail"]


def test_high_risk_gated_by_flag(client, db):
    h = _admin_headers(client, db)
    pid = _mk_project(client, h, "高危项目")
    risky = {"caseName": "清数据", "targetAppPackage": "com.a",
             "operationLog": {"steps": [
                 {"operationNode": None,
                  "operationMethod": {"actionEnum": "CLEAR_DATA", "operationParam": {"text": ""},
                                      "encrypt": False, "safeEncrypt": False},
                  "operationIndex": 0, "operationId": "g1", "stepId": "s1"}]}}
    r = client.post(f"/api/projects/{pid}/app-scripts", headers=h, json={"case": risky})
    assert r.status_code == 400
    assert "高危" in r.json()["detail"] and "CLEAR_DATA" in r.json()["detail"]
    r2 = client.post(f"/api/projects/{pid}/app-scripts", headers=h,
                     json={"case": risky, "allow_high_risk": True})
    assert r2.status_code == 201


def test_list_get_update_delete_flow(client, db):
    h = _admin_headers(client, db)
    pid = _mk_project(client, h, "流程项目")
    sid = client.post(f"/api/projects/{pid}/app-scripts", headers=h, json={"case": _CASE}).json()["id"]
    assert len(client.get(f"/api/projects/{pid}/app-scripts", headers=h).json()) == 1
    assert client.get(f"/api/app-scripts/{sid}", headers=h).status_code == 200
    r = client.put(f"/api/app-scripts/{sid}", headers=h,
                   json={"name": "改名", "description": "备注"})
    assert r.json()["name"] == "改名"
    assert client.delete(f"/api/app-scripts/{sid}", headers=h).status_code == 204
    assert client.get(f"/api/app-scripts/{sid}", headers=h).status_code == 404
    # 列表也不再见软删行
    assert client.get(f"/api/projects/{pid}/app-scripts", headers=h).json() == []


def test_viewer_cannot_write(client, db_session, make_user):
    """viewer 403:建号/赋权方式照抄 tests/test_jobs_repo_isolation.py 的 _auth 同型 helper。"""
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "viewer项目")
    vh = _auth(client, db_session, make_user, "appviewer", project_ids=[pid], role="viewer")
    r = client.post(f"/api/projects/{pid}/app-scripts", headers=vh, json={"case": _CASE})
    assert r.status_code == 403
