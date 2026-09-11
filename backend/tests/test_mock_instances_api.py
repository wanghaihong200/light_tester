"""实例 API:CRUD 权限/端口自动分配与预检/运行中端口锁/启停状态(计划 13 T6)。

对 brief 样例的仓内现状对齐(非行为偏离):
- 登录响应字段是 token 不是 access_token(app/routers/auth.py:LoginOut(token=…),同
  tests/test_app_scripts_api.py 已对齐过的笔误);
- mock_instances/mocks 相关表已在 conftest._TABLES,无需本文件再加 TRUNCATE 清理。
"""
from unittest.mock import patch

from app.models import MockInstance, Project, ProjectMember


def _login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "pw-" + username})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _project_with_member(db, name, user, role="owner"):
    p = Project(name=name)
    db.add(p)
    db.commit()
    db.add(ProjectMember(project_id=p.id, user_id=user.id, role=role))
    db.commit()
    return p


def test_create_auto_alloc_port_and_viewer_forbidden(client, db_session, make_user):
    admin = make_user(db_session, "adm1", is_admin=True)
    viewer = make_user(db_session, "vw1")
    p = _project_with_member(db_session, "p-inst-1", admin)
    db_session.add(ProjectMember(project_id=p.id, user_id=viewer.id, role="viewer"))
    db_session.commit()

    vh = _login(client, viewer.username)
    r = client.post(f"/api/projects/{p.id}/mock-instances", json={"name": "x"}, headers=vh)
    assert r.status_code == 403

    ah = _login(client, admin.username)
    r2 = client.post(f"/api/projects/{p.id}/mock-instances", json={"name": "用户服务"},
                     headers=ah)
    assert r2.status_code == 201
    body = r2.json()
    assert 9001 <= body["port"] <= 9499
    assert body["status"] == "stopped" and body["desired"] == "stopped"


def test_create_conflicting_port_400(client, db_session, make_user):
    admin = make_user(db_session, "adm2", is_admin=True)
    p = _project_with_member(db_session, "p-inst-2", admin)
    db_session.add(MockInstance(project_id=p.id, name="a", port=9001, token="t" * 32))
    db_session.commit()
    h = _login(client, admin.username)
    r = client.post(f"/api/projects/{p.id}/mock-instances",
                    json={"name": "b", "port": 9001}, headers=h)
    assert r.status_code == 400


def test_port_out_of_range_rejected(client, db_session, make_user):
    """端口边界 1-65535:越界 422(Pydantic),port=0 不再落库。
    修复前 70000 会打穿 bind_ok(OverflowError 非 OSError)→ 500;0 会试绑成功直接 201/200。"""
    admin = make_user(db_session, "adm11", is_admin=True)
    p = _project_with_member(db_session, "p-inst-7", admin)
    inst = MockInstance(project_id=p.id, name="a", port=9009, token="t" * 32)
    db_session.add(inst)
    db_session.commit()
    h = _login(client, admin.username)
    assert client.post(f"/api/projects/{p.id}/mock-instances",
                       json={"name": "b", "port": 70000}, headers=h).status_code == 422
    assert client.put(f"/api/mock-instances/{inst.id}",
                      json={"port": 70000}, headers=h).status_code == 422
    assert client.post(f"/api/projects/{p.id}/mock-instances",
                       json={"name": "c", "port": 0}, headers=h).status_code == 422
    assert client.put(f"/api/mock-instances/{inst.id}",
                      json={"port": 0}, headers=h).status_code == 422
    # 边界值 1 与 65535 合法(不实际启动,只落库 stopped)
    lo = client.post(f"/api/projects/{p.id}/mock-instances",
                     json={"name": "d", "port": 1}, headers=h)
    assert lo.status_code == 201 and lo.json()["port"] == 1


def test_port_edit_requires_stopped(client, db_session, make_user):
    admin = make_user(db_session, "adm3", is_admin=True)
    p = _project_with_member(db_session, "p-inst-3", admin)
    inst = MockInstance(project_id=p.id, name="a", port=9002, token="t" * 32, status="running")
    db_session.add(inst)
    db_session.commit()
    h = _login(client, admin.username)
    r = client.put(f"/api/mock-instances/{inst.id}", json={"port": 9003}, headers=h)
    assert r.status_code == 409
    r2 = client.put(f"/api/mock-instances/{inst.id}", json={"name": "b"}, headers=h)
    assert r2.status_code == 200 and r2.json()["name"] == "b"   # 非端口字段运行中可改


def test_delete_running_conflict_and_soft_delete(client, db_session, make_user):
    admin = make_user(db_session, "adm4", is_admin=True)
    p = _project_with_member(db_session, "p-inst-4", admin)
    running = MockInstance(project_id=p.id, name="a", port=9004, token="t" * 32, status="running")
    stopped = MockInstance(project_id=p.id, name="b", port=9005, token="t" * 32)
    db_session.add_all([running, stopped])
    db_session.commit()
    h = _login(client, admin.username)
    assert client.delete(f"/api/mock-instances/{running.id}", headers=h).status_code == 409
    assert client.delete(f"/api/mock-instances/{stopped.id}", headers=h).status_code == 204
    assert client.get(f"/api/mock-instances/{stopped.id}", headers=h).status_code == 404


def test_non_member_404_and_member_viewer_can_read(client, db_session, make_user):
    admin = make_user(db_session, "adm5", is_admin=True)
    outsider = make_user(db_session, "out5")
    p = _project_with_member(db_session, "p-inst-5", admin)
    db_session.add(ProjectMember(project_id=p.id, user_id=outsider.id, role="viewer"))
    db_session.commit()
    inst = MockInstance(project_id=p.id, name="a", port=9006, token="t" * 32)
    db_session.add(inst)
    db_session.commit()
    oh = _login(client, outsider.username)
    # outsider 是本项目 viewer:可读
    assert client.get(f"/api/mock-instances/{inst.id}", headers=oh).status_code == 200
    # 非成员项目实例:404 不泄漏(hidden_p 对 outsider 无任何成员关系)
    hidden_owner = make_user(db_session, "hid5", is_admin=True)
    hidden_p = _project_with_member(db_session, "p-inst-5-hidden", hidden_owner)
    inst2 = MockInstance(project_id=hidden_p.id, name="ghost", port=9007, token="t" * 32)
    db_session.add(inst2)
    db_session.commit()
    assert client.get(f"/api/mock-instances/{inst2.id}", headers=oh).status_code == 404


def test_start_stop_endpoints_via_supervisor_mock(client, db_session, make_user):
    admin = make_user(db_session, "adm6", is_admin=True)
    p = _project_with_member(db_session, "p-inst-6", admin)
    inst = MockInstance(project_id=p.id, name="a", port=9008, token="t" * 32)
    db_session.add(inst)
    db_session.commit()
    h = _login(client, admin.username)

    def fake_start(db, i):
        i.status = "running"
        return "running", None

    def fake_stop(db, i):
        i.status = "stopped"
        i.desired = "stopped"

    with patch("app.routers.mock.supervisor.start_instance", fake_start), \
         patch("app.routers.mock.supervisor.stop_instance", fake_stop):
        r = client.post(f"/api/mock-instances/{inst.id}/start", headers=h)
        assert r.status_code == 200 and r.json()["status"] == "running"
        r2 = client.post(f"/api/mock-instances/{inst.id}/stop", headers=h)
        assert r2.status_code == 200 and r2.json()["status"] == "stopped"


def test_update_instance_passthrough_fields(client, db_session, make_user):
    admin = make_user(db_session, "adm7", is_admin=True)
    p = _project_with_member(db_session, "p-inst-8", admin)
    inst = MockInstance(project_id=p.id, name="a", port=9101, token="t" * 32)
    db_session.add(inst)
    db_session.commit()
    h = _login(client, admin.username)
    r = client.put(f"/api/mock-instances/{inst.id}",
                   json={"passthrough_enabled": True, "upstream_base_url": "http://real:8080"},
                   headers=h)
    assert r.status_code == 200
    assert r.json()["passthrough_enabled"] is True
    assert r.json()["upstream_base_url"] == "http://real:8080"


def test_update_instance_passthrough_requires_url(client, db_session, make_user):
    """开启透传必须给非空 upstream_base_url;非空时须以 http:// 或 https:// 开头。"""
    admin = make_user(db_session, "adm8", is_admin=True)
    p = _project_with_member(db_session, "p-inst-9", admin)
    inst = MockInstance(project_id=p.id, name="a", port=9102, token="t" * 32)
    db_session.add(inst)
    db_session.commit()
    h = _login(client, admin.username)
    r1 = client.put(f"/api/mock-instances/{inst.id}",
                    json={"passthrough_enabled": True}, headers=h)
    assert r1.status_code == 400
    assert r1.json()["detail"] == "开启透传必须填写上游 base_url"
    r2 = client.put(f"/api/mock-instances/{inst.id}",
                    json={"passthrough_enabled": True, "upstream_base_url": "ftp://x"}, headers=h)
    assert r2.status_code == 400
    assert r2.json()["detail"] == "上游 base_url 须以 http:// 或 https:// 开头"


def test_update_instance_disable_keeps_url(client, db_session, make_user):
    """关开关保留地址:临时切回纯 mock 模式不必重填。"""
    admin = make_user(db_session, "adm9", is_admin=True)
    p = _project_with_member(db_session, "p-inst-10", admin)
    inst = MockInstance(project_id=p.id, name="a", port=9103, token="t" * 32)
    db_session.add(inst)
    db_session.commit()
    h = _login(client, admin.username)
    client.put(f"/api/mock-instances/{inst.id}",
               json={"passthrough_enabled": True, "upstream_base_url": "http://real:8080"},
               headers=h)
    r = client.put(f"/api/mock-instances/{inst.id}",
                   json={"passthrough_enabled": False}, headers=h)
    assert r.status_code == 200
    assert r.json()["passthrough_enabled"] is False
    assert r.json()["upstream_base_url"] == "http://real:8080"
