"""计划 16 Task 13:Jenkins 连接配置(admin 门槛 + upsert + 连通测试)。"""
from app.models import JenkinsConnection


def _auth(client, db_session, make_user, name, *, admin=False):
    make_user(db_session, name, is_admin=admin)
    db_session.commit()
    r = client.post("/api/auth/login", json={"username": name, "password": "pw-" + name})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_non_admin_forbidden(client, db_session, make_user):
    h = _auth(client, db_session, make_user, "plain")
    body = {"base_url": "http://x", "api_user": "a", "api_token": "t"}
    assert client.get("/api/jenkins/connection", headers=h).status_code == 403
    # body 合法(否则 422 先于权限检查),403 必须来自 admin 门槛
    assert client.put("/api/jenkins/connection", json=body, headers=h).status_code == 403
    assert client.post("/api/jenkins/connection/test", headers=h).status_code == 403


def test_get_default_and_upsert(client, db_session, make_user):
    h = _auth(client, db_session, make_user, "root1", admin=True)
    d = client.get("/api/jenkins/connection", headers=h).json()
    assert d["configured"] is False
    body = {"base_url": "http://localhost:8081", "api_user": "admin", "api_token": "tok",
            "gitlab_exposed_base": "http://host.docker.internal:8090",
            "credential_id": "gitlab-creds"}
    r = client.put("/api/jenkins/connection", json=body, headers=h)
    assert r.status_code == 200 and r.json()["configured"] is True
    # 再 PUT 覆盖(单行不新增)
    body2 = {**body, "api_token": "tok2"}
    client.put("/api/jenkins/connection", json=body2, headers=h)
    assert client.get("/api/jenkins/connection", headers=h).json()["api_token"] == "tok2"


def test_connection_test_endpoint(client, db_session, make_user, monkeypatch):
    h = _auth(client, db_session, make_user, "root2", admin=True)
    db_session.add(JenkinsConnection(id=1, base_url="http://jk", api_user="a", api_token="t"))
    db_session.commit()

    class FakeOk:
        def __enter__(self): return self
        def __exit__(self, *a): return None
        def test_connection(self): return {"ok": True}

    from app.cicd import executor
    monkeypatch.setattr(executor, "client_from", lambda conn: FakeOk())
    assert client.post("/api/jenkins/connection/test", headers=h).json() == {"ok": True}

    from app.cicd.jenkins_client import JenkinsError

    class FakeBad(FakeOk):
        def test_connection(self): raise JenkinsError("Jenkins 不可达: x")

    monkeypatch.setattr(executor, "client_from", lambda conn: FakeBad())
    r = client.post("/api/jenkins/connection/test", headers=h)
    assert r.status_code == 400 and "不可达" in r.json()["detail"]
