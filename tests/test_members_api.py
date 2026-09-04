"""Task 9:项目成员管理 API(owner 分配/角色变更/末位 owner 守卫/权限闸先于用户存在性检查)。"""


def _admin_headers(client, db_session):
    """bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    """建用户(已存在则复用,否则与 unique 约束冲突)+分配项目+登录,返回 Authorization 头。"""
    from app.models import Project, ProjectMember, User

    u = db_session.query(User).filter(User.username == name).first()
    if u is None:
        u = make_user(db_session, name)
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


def test_owner_manages_members(client, db_session, make_user):
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    ah = {"Authorization": f"Bearer {atok}"}
    pid = client.post("/api/projects", json={"name": "mgt"}, headers=ah).json()["id"]
    make_user(db_session, "bob")
    r = client.post(f"/api/projects/{pid}/members", json={"username": "bob", "role": "editor"}, headers=ah)
    assert r.status_code == 201 and r.json()["role"] == "editor"
    # 重复添加 409
    assert client.post(f"/api/projects/{pid}/members",
                       json={"username": "bob", "role": "viewer"}, headers=ah).status_code == 409
    # bob(editor)不能管成员——对不存在的用户名 x1 添加,也必须 403(权限闸先于用户存在性检查)
    bh = _auth(client, db_session, make_user, "bob")  # 借 helper 登录已存在的 bob
    r = client.post(f"/api/projects/{pid}/members", json={"username": "x1", "role": "viewer"}, headers=bh)
    assert r.status_code == 403
    # 列表 viewer 可读
    assert client.get(f"/api/projects/{pid}/members", headers=bh).status_code == 200


def test_list_returns_joined_user_fields(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "roster"}, headers=ah).json()["id"]
    make_user(db_session, "cara")
    client.post(f"/api/projects/{pid}/members", json={"username": "cara", "role": "viewer"}, headers=ah)
    data = client.get(f"/api/projects/{pid}/members", headers=ah).json()
    cara = next(m for m in data if m["username"] == "cara")
    assert cara["role"] == "viewer" and cara["display_name"] == "cara"
    assert {"id", "user_id", "username", "display_name", "role"} <= set(cara)


def test_owner_changes_role(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "promote"}, headers=ah).json()["id"]
    pat = make_user(db_session, "pat")
    client.post(f"/api/projects/{pid}/members", json={"username": "pat", "role": "viewer"}, headers=ah)
    r = client.put(f"/api/projects/{pid}/members/{pat.id}", json={"role": "editor"}, headers=ah)
    assert r.status_code == 200 and r.json()["role"] == "editor"


def test_last_owner_cannot_demote_self(client, db_session, make_user):
    from app.bootstrap import ensure_bootstrap_admin
    from app.models import Project, ProjectMember

    ensure_bootstrap_admin(db_session)
    owner = make_user(db_session, "solo")
    p = Project(name="solo-p")
    db_session.add(p)
    db_session.flush()
    db_session.add(ProjectMember(project_id=p.id, user_id=owner.id, role="owner"))
    db_session.commit()
    tok = client.post("/api/auth/login", json={"username": "solo", "password": "pw-solo"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    r = client.put(f"/api/projects/{p.id}/members/{owner.id}", json={"role": "viewer"}, headers=h)
    assert r.status_code == 409


def test_delete_member_and_last_owner_guard(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "removal"}, headers=ah).json()["id"]
    gone = make_user(db_session, "gone")
    client.post(f"/api/projects/{pid}/members", json={"username": "gone", "role": "editor"}, headers=ah)
    assert client.delete(f"/api/projects/{pid}/members/{gone.id}", headers=ah).status_code == 204
    # admin 自己是该项目唯一 owner,自删同样被末位 owner 守卫拦下(admin 也受不变式约束)
    from app.models import User

    admin = db_session.query(User).filter_by(username="admin").first()
    r = client.delete(f"/api/projects/{pid}/members/{admin.id}", headers=ah)
    assert r.status_code == 409 and r.json()["detail"] == "项目至少需要一名 owner"


def test_outsider_members_invisible_404(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "closed"}, headers=ah).json()["id"]
    oh = _auth(client, db_session, make_user, "stranger")
    assert client.get(f"/api/projects/{pid}/members", headers=oh).status_code == 404
    assert client.post(f"/api/projects/{pid}/members",
                       json={"username": "stranger", "role": "viewer"}, headers=oh).status_code == 404
