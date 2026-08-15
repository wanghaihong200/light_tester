def test_create_and_get_project(client):
    resp = client.post(
        "/api/projects", json={"name": "商城系统", "description": "被测系统A"}
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    resp = client.get(f"/api/projects/{pid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "商城系统"
    assert "git_token" not in body  # 列表/详情不回显 token


def test_duplicate_name_rejected(client):
    client.post("/api/projects", json={"name": "P"})
    resp = client.post("/api/projects", json={"name": "P"})
    assert resp.status_code == 409


def test_update_project(client):
    pid = client.post("/api/projects", json={"name": "old"}).json()["id"]
    resp = client.put(
        f"/api/projects/{pid}",
        json={"name": "new", "git_repo_url": "http://gitlab.example/repo.git"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new"


def test_delete_project(client):
    pid = client.post("/api/projects", json={"name": "bye"}).json()["id"]
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404


def test_rename_duplicate_name_409(client):
    p1 = client.post("/api/projects", json={"name": "Alpha"}).json()["id"]
    client.post("/api/projects", json={"name": "Beta"})
    resp = client.put(f"/api/projects/{p1}", json={"name": "Beta"})
    assert resp.status_code == 409


def test_rename_fresh_name_200(client):
    p1 = client.post("/api/projects", json={"name": "Alpha"}).json()["id"]
    resp = client.put(f"/api/projects/{p1}", json={"name": "Gamma"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Gamma"
