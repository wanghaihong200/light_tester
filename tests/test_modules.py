import pytest


@pytest.fixture()
def pid(client):
    return client.post("/api/projects", json={"name": "P"}).json()["id"]


def test_create_nested_modules(client, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "登录"}).json()
    child = client.post(
        f"/api/projects/{pid}/modules", json={"name": "扫码登录", "parent_id": root["id"]}
    ).json()
    assert child["parent_id"] == root["id"]


def test_tree_returns_nested_structure(client, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "登录"}).json()
    client.post(f"/api/projects/{pid}/modules", json={"name": "扫码登录", "parent_id": root["id"]})
    tree = client.get(f"/api/projects/{pid}/tree").json()
    assert len(tree) == 1
    assert tree[0]["name"] == "登录"
    assert [c["name"] for c in tree[0]["children"]] == ["扫码登录"]
    assert tree[0]["feature_points"] == []


def test_move_module_forbidden_to_own_descendant(client, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "root"}).json()
    child = client.post(
        f"/api/projects/{pid}/modules", json={"name": "child", "parent_id": root["id"]}
    ).json()
    resp = client.put(f"/api/modules/{root['id']}", json={"parent_id": child["id"]})
    assert resp.status_code == 400


def test_delete_module_cascades(client, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "root"}).json()
    child = client.post(
        f"/api/projects/{pid}/modules", json={"name": "child", "parent_id": root["id"]}
    ).json()
    client.delete(f"/api/modules/{root['id']}")
    tree = client.get(f"/api/projects/{pid}/tree").json()
    assert tree == []
