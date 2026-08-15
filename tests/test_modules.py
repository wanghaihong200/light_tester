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


def test_move_to_other_project_parent_400(client):
    # Two projects, each with a root module
    p1 = client.post("/api/projects", json={"name": "ProjA"}).json()["id"]
    p2 = client.post("/api/projects", json={"name": "ProjB"}).json()["id"]
    mod_a = client.post(f"/api/projects/{p1}/modules", json={"name": "modA"}).json()
    mod_b = client.post(f"/api/projects/{p2}/modules", json={"name": "modB"}).json()
    resp = client.put(f"/api/modules/{mod_a['id']}", json={"parent_id": mod_b["id"]})
    assert resp.status_code == 400
    assert "invalid parent_id" in resp.json()["detail"]


def test_tree_includes_case_summary(client, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "登录"}).json()
    child = client.post(
        f"/api/projects/{pid}/modules", json={"name": "扫码登录", "parent_id": root["id"]}
    ).json()
    fp = client.post(
        f"/api/modules/{child['id']}/feature-points", json={"name": "扫码功能"}
    ).json()
    case_resp = client.post(
        f"/api/feature-points/{fp['id']}/cases",
        json={"title": "验证码正确登录", "priority": "P0"},
    )
    assert case_resp.status_code == 201

    tree = client.get(f"/api/projects/{pid}/tree").json()
    assert len(tree) == 1
    assert tree[0]["name"] == "登录"
    assert len(tree[0]["children"]) == 1
    child_node = tree[0]["children"][0]
    assert child_node["name"] == "扫码登录"
    assert len(child_node["feature_points"]) == 1
    fp_node = child_node["feature_points"][0]
    assert fp_node["name"] == "扫码功能"
    assert len(fp_node["cases"]) == 1
    case_node = fp_node["cases"][0]
    assert case_node["title"] == "验证码正确登录"
    assert case_node["priority"] == "P0"
    assert "executed_pass" in case_node
