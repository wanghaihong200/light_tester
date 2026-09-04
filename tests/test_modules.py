import pytest


@pytest.fixture()
def ah(client, db_session):
    """Task 6 存量用例补鉴权(保语义,补鉴权):bootstrap admin 登录头,admin 对所有项目直通。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def pid(client, ah):
    return client.post("/api/projects", json={"name": "P"}, headers=ah).json()["id"]


def test_create_nested_modules(client, ah, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "登录"}, headers=ah).json()
    child = client.post(
        f"/api/projects/{pid}/modules", json={"name": "扫码登录", "parent_id": root["id"]}, headers=ah
    ).json()
    assert child["parent_id"] == root["id"]


def test_tree_returns_nested_structure(client, ah, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "登录"}, headers=ah).json()
    client.post(f"/api/projects/{pid}/modules", json={"name": "扫码登录", "parent_id": root["id"]}, headers=ah)
    tree = client.get(f"/api/projects/{pid}/tree", headers=ah).json()
    assert len(tree) == 1
    assert tree[0]["name"] == "登录"
    assert [c["name"] for c in tree[0]["children"]] == ["扫码登录"]
    assert tree[0]["feature_points"] == []


def test_move_module_forbidden_to_own_descendant(client, ah, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "root"}, headers=ah).json()
    child = client.post(
        f"/api/projects/{pid}/modules", json={"name": "child", "parent_id": root["id"]}, headers=ah
    ).json()
    resp = client.put(f"/api/modules/{root['id']}", json={"parent_id": child["id"]}, headers=ah)
    assert resp.status_code == 400


def test_delete_module_cascades(client, ah, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "root"}, headers=ah).json()
    child = client.post(
        f"/api/projects/{pid}/modules", json={"name": "child", "parent_id": root["id"]}, headers=ah
    ).json()
    client.delete(f"/api/modules/{root['id']}", headers=ah)
    tree = client.get(f"/api/projects/{pid}/tree", headers=ah).json()
    assert tree == []


def test_move_to_other_project_parent_400(client, ah):
    # Two projects, each with a root module
    p1 = client.post("/api/projects", json={"name": "ProjA"}, headers=ah).json()["id"]
    p2 = client.post("/api/projects", json={"name": "ProjB"}, headers=ah).json()["id"]
    mod_a = client.post(f"/api/projects/{p1}/modules", json={"name": "modA"}, headers=ah).json()
    mod_b = client.post(f"/api/projects/{p2}/modules", json={"name": "modB"}, headers=ah).json()
    resp = client.put(f"/api/modules/{mod_a['id']}", json={"parent_id": mod_b["id"]}, headers=ah)
    assert resp.status_code == 400
    assert "invalid parent_id" in resp.json()["detail"]


def test_tree_includes_case_summary(client, ah, pid):
    root = client.post(f"/api/projects/{pid}/modules", json={"name": "登录"}, headers=ah).json()
    child = client.post(
        f"/api/projects/{pid}/modules", json={"name": "扫码登录", "parent_id": root["id"]}, headers=ah
    ).json()
    fp = client.post(
        f"/api/modules/{child['id']}/feature-points", json={"name": "扫码功能"}, headers=ah
    ).json()
    case_resp = client.post(
        f"/api/feature-points/{fp['id']}/cases",
        json={"title": "验证码正确登录", "priority": "P0"},
        headers=ah,
    )
    assert case_resp.status_code == 201

    tree = client.get(f"/api/projects/{pid}/tree", headers=ah).json()
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
