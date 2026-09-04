# UI自动化脚本 CRUD API 测试:创建/列表/详情/更新/软删 + 项目隔离
# Task 8 补鉴权:业务端点全量 401 后,setup/请求统一走 admin 头(保语义,补鉴权)
from app.database import SessionLocal
from app.models import UiScript


def _admin_headers(client):
    from app.bootstrap import ensure_bootstrap_admin
    from app.database import SessionLocal as SL

    db = SL()
    try:
        ensure_bootstrap_admin(db)
    finally:
        db.close()
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _mk_project(client, ah, name="ui-crud-p"):
    return client.post("/api/projects", json={"name": name}, headers=ah).json()


DOC = {"version": 1, "meta": {"start_url": "https://x.com"}, "variables": [], "steps": []}


def test_script_crud_roundtrip(client):
    ah = _admin_headers(client)
    pid = _mk_project(client, ah)["id"]
    r = client.post(f"/api/projects/{pid}/ui-scripts", json={"name": "登录", "script": DOC}, headers=ah)
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["script"]["version"] == 1

    lst = client.get(f"/api/projects/{pid}/ui-scripts", headers=ah).json()
    assert [s["id"] for s in lst] == [sid]

    up = client.put(f"/api/ui-scripts/{sid}", json={"name": "登录2", "description": "d", "script": DOC}, headers=ah)
    assert up.status_code == 200 and up.json()["name"] == "登录2"

    assert client.delete(f"/api/ui-scripts/{sid}", headers=ah).status_code == 204
    assert client.get(f"/api/ui-scripts/{sid}", headers=ah).status_code == 404  # 软删后视为不存在


def test_delete_is_soft_delete_row_retained(client):
    ah = _admin_headers(client)
    # 软删实证:DELETE 只置 is_deleted,不允许物理删除。
    # 该用例防止实现被"优化"成 db.delete(row) —— 物理删会断掉 ui_runs.script_id 外键历史。
    pid = _mk_project(client, ah, "softdel-row")["id"]
    sid = client.post(f"/api/projects/{pid}/ui-scripts", json={"name": "s", "script": DOC}, headers=ah).json()["id"]
    assert client.delete(f"/api/ui-scripts/{sid}", headers=ah).status_code == 204

    # DELETE 已提交,新开会话直查 DB,避免会话缓存;行必须还在且 is_deleted=True
    db = SessionLocal()
    try:
        row = db.get(UiScript, sid)
        assert row is not None and row.is_deleted is True
    finally:
        db.close()


def test_soft_deleted_script_put_and_delete_404(client):
    ah = _admin_headers(client)
    # 已软删脚本对写操作同样视为不存在:覆盖 _get_owned 的 is_deleted 分支(PUT/DELETE 路径)
    pid = _mk_project(client, ah, "softdel-p")["id"]
    sid = client.post(f"/api/projects/{pid}/ui-scripts", json={"name": "s", "script": DOC}, headers=ah).json()["id"]
    assert client.delete(f"/api/ui-scripts/{sid}", headers=ah).status_code == 204
    assert client.put(f"/api/ui-scripts/{sid}", json={"name": "x", "script": DOC}, headers=ah).status_code == 404
    assert client.delete(f"/api/ui-scripts/{sid}", headers=ah).status_code == 404


def test_script_project_isolation_and_404(client):
    ah = _admin_headers(client)
    p1 = _mk_project(client, ah, "p1")
    p2 = _mk_project(client, ah, "p2")
    sid = client.post(f"/api/projects/{p1['id']}/ui-scripts", json={"name": "a", "script": DOC}, headers=ah).json()["id"]
    assert client.get(f"/api/ui-scripts/{sid}", headers=ah).json()["project_id"] == p1["id"]
    assert client.put(f"/api/ui-scripts/{sid}", json={"name": "b", "script": DOC}, headers=ah).status_code == 200
    assert client.post("/api/projects/99999/ui-scripts", json={"name": "x", "script": DOC}, headers=ah).status_code == 404
