"""计划 16 Task 9:执行计划 CRUD + 选择集合富化 + 权限。"""
from app.models import Project, ProjectMember


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    u = make_user(db_session, name)
    for pid in project_ids:
        db_session.add(ProjectMember(project_id=pid, user_id=u.id, role=role))
    db_session.commit()
    r = client.post("/api/auth/login", json={"username": name, "password": "pw-" + name})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _mk_project(db_session, name="P16") -> int:
    p = Project(name=name)
    db_session.add(p)
    db_session.commit()
    return p.id


UI_BODY = {
    "name": "UI 冒烟",
    "kind": "ui",
    "branch": "master",
    "selection": [{"file_path": "tests/test_smoke.py", "function": "test_login"}],
}
API_BODY = {
    "name": "接口回归",
    "kind": "api",
    "branch": "master",
    "selection": [{"class_name": "com.x.AuthApiTest", "method": "loginOk"}],
}


def test_create_ui_plan_stores_nodeid_selection(client, db_session, make_user):
    """计划 17 T5:ui 选择项按 nodeid 语义原样存 {file_path, function}(不再富化 file)。"""
    pid = _mk_project(db_session)
    h = _auth(client, db_session, make_user, "planner", project_ids=[pid])
    r = client.post(f"/api/projects/{pid}/ci-plans", json=UI_BODY, headers=h)
    assert r.status_code == 201
    assert r.json()["selection"] == [{"file_path": "tests/test_smoke.py",
                                      "function": "test_login"}]


def test_create_api_plan_enriches_ref(client, db_session, make_user):
    pid = _mk_project(db_session)
    h = _auth(client, db_session, make_user, "planner", project_ids=[pid])
    r = client.post(f"/api/projects/{pid}/ci-plans", json=API_BODY, headers=h)
    assert r.json()["selection"][0]["ref"] == "com.x.AuthApiTest#loginOk"


def test_viewer_cannot_create_but_can_list(client, db_session, make_user):
    pid = _mk_project(db_session)
    hv = _auth(client, db_session, make_user, "viewonly", project_ids=[pid], role="viewer")
    assert client.post(f"/api/projects/{pid}/ci-plans", json=UI_BODY, headers=hv).status_code == 403
    he = _auth(client, db_session, make_user, "edit2", project_ids=[pid])
    client.post(f"/api/projects/{pid}/ci-plans", json=UI_BODY, headers=he)
    assert client.get(f"/api/projects/{pid}/ci-plans", headers=hv).status_code == 200


def test_non_member_gets_404(client, db_session, make_user):
    pid = _mk_project(db_session)
    h = _auth(client, db_session, make_user, "outsider")
    assert client.get(f"/api/projects/{pid}/ci-plans", headers=h).status_code == 404


def test_update_and_soft_delete(client, db_session, make_user):
    pid = _mk_project(db_session)
    h = _auth(client, db_session, make_user, "edit3", project_ids=[pid])
    plan_id = client.post(f"/api/projects/{pid}/ci-plans", json=API_BODY, headers=h).json()["id"]
    r = client.put(f"/api/ci-plans/{plan_id}",
                   json={"name": "改名", "selection": [{"class_name": "com.x.A", "method": "m2"}]},
                   headers=h)
    assert r.json()["name"] == "改名" and r.json()["selection"][0]["ref"] == "com.x.A#m2"
    assert client.delete(f"/api/ci-plans/{plan_id}", headers=h).status_code == 204
    assert client.get(f"/api/projects/{pid}/ci-plans", headers=h).json() == []


def test_malformed_selection_400(client, db_session, make_user):
    pid = _mk_project(db_session)
    h = _auth(client, db_session, make_user, "edit4", project_ids=[pid])
    bad = {"name": "x", "kind": "ui", "branch": "m", "selection": [{"script_id": "abc"}]}
    assert client.post(f"/api/projects/{pid}/ci-plans", json=bad, headers=h).status_code == 400
