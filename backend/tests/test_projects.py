import pytest


@pytest.fixture()
def ah(client, db_session):
    """Task 5 存量用例补鉴权(保语义,补鉴权):bootstrap admin 登录头,admin 对所有项目直通。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_create_and_get_project(client, ah):
    resp = client.post(
        "/api/projects", json={"name": "商城系统", "description": "被测系统A"}, headers=ah
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    resp = client.get(f"/api/projects/{pid}", headers=ah)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "商城系统"
    assert "git_token" not in body  # 列表/详情不回显 token


def test_duplicate_name_rejected(client, ah):
    client.post("/api/projects", json={"name": "P"}, headers=ah)
    resp = client.post("/api/projects", json={"name": "P"}, headers=ah)
    assert resp.status_code == 409


def test_update_project(client, ah):
    pid = client.post("/api/projects", json={"name": "old"}, headers=ah).json()["id"]
    resp = client.put(
        f"/api/projects/{pid}",
        json={"name": "new", "git_repo_url": "http://gitlab.example/repo.git"},
        headers=ah,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new"


def test_delete_project(client, ah):
    pid = client.post("/api/projects", json={"name": "bye"}, headers=ah).json()["id"]
    assert client.delete(f"/api/projects/{pid}", headers=ah).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=ah).status_code == 404


def test_rename_duplicate_name_409(client, ah):
    p1 = client.post("/api/projects", json={"name": "Alpha"}, headers=ah).json()["id"]
    client.post("/api/projects", json={"name": "Beta"}, headers=ah)
    resp = client.put(f"/api/projects/{p1}", json={"name": "Beta"}, headers=ah)
    assert resp.status_code == 409


def test_rename_fresh_name_200(client, ah):
    p1 = client.post("/api/projects", json={"name": "Alpha"}, headers=ah).json()["id"]
    resp = client.put(f"/api/projects/{p1}", json={"name": "Gamma"}, headers=ah)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Gamma"
