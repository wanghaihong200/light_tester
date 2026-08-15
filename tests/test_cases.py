import pytest


@pytest.fixture()
def fp_id(client):
    pid = client.post("/api/projects", json={"name": "P"}).json()["id"]
    mid = client.post(f"/api/projects/{pid}/modules", json={"name": "登录"}).json()["id"]
    return client.post(f"/api/modules/{mid}/feature-points", json={"name": "账号密码登录"}).json()["id"]


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


def test_create_and_get_case_with_steps(client, fp_id):
    resp = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload())
    assert resp.status_code == 201
    cid = resp.json()["id"]

    body = client.get(f"/api/cases/{cid}").json()
    assert body["title"] == "正确账号密码登录成功"
    assert body["executed_pass"] is None
    assert [s["step_no"] for s in body["steps"]] == [1, 2]
    assert body["steps"][0]["expected"] == "密码框显示为掩码"


def test_priority_validation(client, fp_id):
    resp = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload(priority="P9"))
    assert resp.status_code == 422


def test_update_case_replaces_steps(client, fp_id):
    cid = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload()).json()["id"]
    resp = client.put(
        f"/api/cases/{cid}",
        json=_case_payload(
            title="改标题",
            steps=[{"action": "仅一步", "expected": "仅一个预期"}],
        ),
    )
    assert resp.status_code == 200
    body = client.get(f"/api/cases/{cid}").json()
    assert body["title"] == "改标题"
    assert len(body["steps"]) == 1
    assert body["steps"][0]["step_no"] == 1


def test_execution_toggle(client, fp_id):
    cid = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload()).json()["id"]
    assert client.patch(f"/api/cases/{cid}/execution", json={"executed_pass": True}).status_code == 200
    assert client.get(f"/api/cases/{cid}").json()["executed_pass"] is True
    assert client.patch(f"/api/cases/{cid}/execution", json={"executed_pass": None}).status_code == 200
    assert client.get(f"/api/cases/{cid}").json()["executed_pass"] is None


def test_delete_feature_point_cascades_cases(client, fp_id):
    cid = client.post(f"/api/feature-points/{fp_id}/cases", json=_case_payload()).json()["id"]
    client.delete(f"/api/feature-points/{fp_id}")
    assert client.get(f"/api/cases/{cid}").status_code == 404
