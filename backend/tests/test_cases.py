import pytest


@pytest.fixture()
def ah(client, db_session):
    """Task 6 存量用例补鉴权(保语义,补鉴权):bootstrap admin 登录头,admin 对所有项目直通。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def fp_id(client, ah):
    pid = client.post("/api/projects", json={"name": "P"}, headers=ah).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "登录"}, headers=ah).json()["id"]
    return client.post(f"/api/modules/{mid}/feature-points", json={"name": "账号密码登录"}, headers=ah).json()["id"]


def _case_payload(**overrides):
    payload = {
        "title": "正确账号密码登录成功",
        "priority": "P0",
        "precondition": "账号已注册且未锁定",
        "steps": [
            {"action": "输入正确账号密码", "expected": "密码框显示为掩码"},
            {"action": "点击登录按钮", "expected": "跳转到首页,右上角显示用户名"},
        ],
    }
    payload.update(overrides)
    return payload


def test_create_and_get_case_with_steps(client, ah, fp_id):
    resp = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload(), headers=ah)
    assert resp.status_code == 201
    cid = resp.json()["id"]

    body = client.get(f"/api/cases/{cid}", headers=ah).json()
    assert body["title"] == "正确账号密码登录成功"
    assert body["executed_pass"] is None
    assert [s["step_no"] for s in body["steps"]] == [1, 2]
    assert body["steps"][0]["expected"] == "密码框显示为掩码"


def test_priority_validation(client, ah, fp_id):
    resp = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload(priority="P9"), headers=ah)
    assert resp.status_code == 422


def test_update_case_replaces_steps(client, ah, fp_id):
    cid = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload(), headers=ah).json()["id"]
    resp = client.put(
        f"/api/cases/{cid}",
        json=_case_payload(
            title="改标题",
            steps=[{"action": "仅一步", "expected": "仅一个预期"}],
        ),
        headers=ah,
    )
    assert resp.status_code == 200
    body = client.get(f"/api/cases/{cid}", headers=ah).json()
    assert body["title"] == "改标题"
    assert len(body["steps"]) == 1
    assert body["steps"][0]["step_no"] == 1


def test_execution_toggle(client, ah, fp_id):
    cid = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload(), headers=ah).json()["id"]
    assert client.patch(
        f"/api/cases/{cid}/execution", json={"executed_pass": True}, headers=ah
    ).status_code == 200
    assert client.get(f"/api/cases/{cid}", headers=ah).json()["executed_pass"] is True
    assert client.patch(
        f"/api/cases/{cid}/execution", json={"executed_pass": None}, headers=ah
    ).status_code == 200
    assert client.get(f"/api/cases/{cid}", headers=ah).json()["executed_pass"] is None


def test_delete_feature_point_cascades_cases(client, ah, fp_id):
    cid = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload(), headers=ah).json()["id"]
    client.delete(f"/api/feature-points/{fp_id}", headers=ah)
    assert client.get(f"/api/cases/{cid}", headers=ah).status_code == 404
