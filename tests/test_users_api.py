"""Task 10:用户管理 API(admin 建号/重置密码/禁用;非 admin 403;不能禁用自己的账号,改名/自改密放行)。"""


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    """建用户+分配项目+登录,返回 Authorization 头。
    注:简报样例仅特判 list,缺省元组 () 会落到 [()] 使 session.get 报错;
    此处统一归一化(语义不变),复制自 tests/test_project_isolation.py(Task 5 修正版)。"""
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


def test_admin_crud_users(client, db_session):
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    h = {"Authorization": f"Bearer {atok}"}
    r = client.post("/api/users", json={"username": "carol", "display_name": "卡罗", "password": "123456"}, headers=h)
    assert r.status_code == 201
    assert client.post("/api/users", json={"username": "carol", "display_name": "x", "password": "123456"}, headers=h).status_code == 409
    assert client.post("/api/users", json={"username": "dave", "display_name": "x", "password": "123"}, headers=h).status_code == 422
    uid = r.json()["id"]
    assert client.put(f"/api/users/{uid}", json={"is_active": False}, headers=h).status_code == 200
    # carol 登录被拒
    assert client.post("/api/auth/login", json={"username": "carol", "password": "123456"}).status_code == 403


def test_non_admin_forbidden(client, db_session, make_user):
    h = _auth(client, db_session, make_user, "pleb")
    assert client.get("/api/users", headers=h).status_code == 403
    assert client.post("/api/users", json={"username": "x2", "display_name": "x", "password": "123456"}, headers=h).status_code == 403


def test_admin_cannot_disable_self(client, db_session):
    from app.bootstrap import ensure_bootstrap_admin
    from app.models import User

    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    h = {"Authorization": f"Bearer {atok}"}
    aid = db_session.query(User).filter_by(username="admin").first().id
    assert client.put(f"/api/users/{aid}", json={"is_active": False}, headers=h).status_code == 409


def test_admin_can_rename_self(client, db_session):
    """自操作守卫只拦禁用自己:改 display_name 放行(200,收尾修复波收窄)。"""
    from app.bootstrap import ensure_bootstrap_admin
    from app.models import User

    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    h = {"Authorization": f"Bearer {atok}"}
    aid = db_session.query(User).filter_by(username="admin").first().id
    r = client.put(f"/api/users/{aid}", json={"display_name": "新名字"}, headers=h)
    assert r.status_code == 200
    assert r.json()["display_name"] == "新名字"


def test_admin_can_reset_own_password(client, db_session):
    """自改密 200:旧 token 不吊销仍可用(Q6),新密码可登录、旧密码被拒。"""
    from app.bootstrap import ensure_bootstrap_admin
    from app.models import User

    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    h = {"Authorization": f"Bearer {atok}"}
    aid = db_session.query(User).filter_by(username="admin").first().id
    assert client.put(f"/api/users/{aid}", json={"password": "newpass9"}, headers=h).status_code == 200
    # 旧 token 仍有效(设计上不吊销)
    assert client.get("/api/auth/me", headers=h).status_code == 200
    assert client.post("/api/auth/login", json={"username": "admin", "password": "newpass9"}).status_code == 200
    assert client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).status_code == 401


def test_admin_list_users(client, db_session):
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    h = {"Authorization": f"Bearer {atok}"}
    client.post("/api/users", json={"username": "felix", "display_name": "菲利克斯", "password": "123456"}, headers=h)
    rows = client.get("/api/users", headers=h).json()
    by_name = {r["username"]: r for r in rows}
    assert by_name["admin"]["is_admin"] is True
    assert by_name["felix"]["is_admin"] is False and by_name["felix"]["is_active"] is True
    # UserOut 不外泄口令哈希
    assert "password_hash" not in by_name["felix"]


def test_admin_reset_password_and_missing_target(client, db_session):
    """重置密码后新密码可登录、旧密码被拒(Q6:旧 token 不吊销);短密码 422;目标不存在 404。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    h = {"Authorization": f"Bearer {atok}"}
    uid = client.post(
        "/api/users", json={"username": "erin", "display_name": "erin", "password": "123456"}, headers=h
    ).json()["id"]
    assert client.put(f"/api/users/{uid}", json={"password": "newpass1"}, headers=h).status_code == 200
    assert client.post("/api/auth/login", json={"username": "erin", "password": "123456"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "erin", "password": "newpass1"}).status_code == 200
    # 重置密码同样受最短 6 位约束
    assert client.put(f"/api/users/{uid}", json={"password": "abc"}, headers=h).status_code == 422
    assert client.put("/api/users/99999", json={"display_name": "ghost"}, headers=h).status_code == 404


def test_unauthenticated_rejected(client):
    assert client.get("/api/users").status_code == 401
    assert client.post("/api/users", json={"username": "n", "display_name": "n", "password": "123456"}).status_code == 401
