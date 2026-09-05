"""Task 5:projects 路由真隔离(自建自动 owner / 404 不可见 / viewer-editor-owner 分档 / 凭证不外泄)。
_auth helper 供 Task 6-8 复制成同型 helper。"""


def _admin_headers(client, db_session):
    """bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    """建用户+分配项目+登录,返回 Authorization 头。
    注:简报样例仅特判 list,缺省元组 () 会落到 [()] 使 session.get 报错;
    此处统一归一化(语义不变),Task 6-8 复制时请带走本版。"""
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


def test_create_project_grants_owner(client, db_session, make_user):
    h = _auth(client, db_session, make_user, "builder")
    r = client.post("/api/projects", json={"name": "new-proj"}, headers=h)
    assert r.status_code == 201
    from app.models import ProjectMember, User

    u = db_session.query(User).filter(User.username == "builder").first()
    m = db_session.query(ProjectMember).filter_by(user_id=u.id).first()
    assert m is not None and m.role == "owner"


def test_list_filtered_to_memberships(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    h = _auth(client, db_session, make_user, "seer", project_ids=[], role="viewer")
    client.post("/api/projects", json={"name": "mine"}, headers=h)          # 自建可见
    client.post("/api/projects", json={"name": "admin-only"}, headers=ah)   # admin 建第二个
    names = [p["name"] for p in client.get("/api/projects", headers=h).json()]
    assert names == ["mine"]
    assert {p["name"] for p in client.get("/api/projects", headers=ah).json()} >= {"mine", "admin-only"}


def test_invisible_project_is_404_not_403(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    real_pid = client.post("/api/projects", json={"name": "hidden"}, headers=ah).json()["id"]
    h = _auth(client, db_session, make_user, "outsider")
    assert client.get("/api/projects/999999", headers=h).status_code == 404        # 不存在
    assert client.get(f"/api/projects/{real_pid}", headers=h).status_code == 404   # 不可见(非 403/200)


def test_viewer_cannot_edit_admin_can(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "ro-project"}, headers=ah).json()["id"]
    vh = _auth(client, db_session, make_user, "looker", project_ids=[pid], role="viewer")
    assert client.put(f"/api/projects/{pid}", json={"description": "x"}, headers=vh).status_code == 403
    r = client.put(f"/api/projects/{pid}", json={"description": "admin-edit"}, headers=ah)
    assert r.status_code == 200 and r.json()["description"] == "admin-edit"


def test_delete_requires_owner(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "doomed"}, headers=ah).json()["id"]
    eh = _auth(client, db_session, make_user, "worker", project_ids=[pid], role="editor")
    assert client.delete(f"/api/projects/{pid}", headers=eh).status_code == 403
    assert client.delete(f"/api/projects/{pid}", headers=ah).status_code == 204


def test_credential_fields_never_leak(client, db_session):
    ah = _admin_headers(client, db_session)
    pid = client.post(
        "/api/projects", json={"name": "secret-proj", "git_token": "tok-should-not-leak"}, headers=ah
    ).json()["id"]
    body = client.get(f"/api/projects/{pid}", headers=ah).json()
    assert "git_token" not in body and "storage_state" not in body
