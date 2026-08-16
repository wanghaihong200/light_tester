import io
import json
import zipfile

import pytest


@pytest.fixture()
def seeded_pid(client):
    """API 种树(仓库既有模式):项目 → 登录模块 → 子模块 + 功能点 → P0 用例(1 步,已执行通过)。"""
    pid = client.post("/api/projects", json={"name": "导出测试项目"}).json()["id"]
    m1 = client.post(f"/api/projects/{pid}/modules", json={"name": "登录模块"}).json()
    client.post(f"/api/projects/{pid}/modules", json={"name": "子模块", "parent_id": m1["id"]})
    fp = client.post(f"/api/modules/{m1['id']}/feature-points", json={"name": "账号登录"}).json()
    case = client.post(
        f"/api/feature-points/{fp['id']}/cases",
        json={
            "title": "正确账号密码登录成功",
            "priority": "P0",
            "precondition": "已注册用户",
            "remark": "冒烟用例",
            "steps": [{"action": "输入账号密码", "expected": "登录成功"}],
        },
    ).json()
    client.patch(f"/api/cases/{case['id']}/execution", json={"executed_pass": True})
    return pid


def _content(resp) -> dict:
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        assert "content.json" in z.namelist()
        assert "metadata.json" in z.namelist()
        return json.loads(z.read("content.json"))


def test_export_xmind_structure(client, seeded_pid):
    resp = client.get(f"/api/projects/{seeded_pid}/export/xmind")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/octet-stream")
    assert "attachment" in resp.headers["content-disposition"]

    root = _content(resp)[0]["rootTopic"]
    assert root["title"] == "导出测试项目"
    assert [t["title"] for t in root["children"]["attached"]] == ["登录模块"]
    m1 = root["children"]["attached"][0]
    assert [t["title"] for t in m1["children"]["attached"]] == ["子模块", "账号登录"]  # 子模块在前、功能点在后(与前端一致)
    fp_topic = m1["children"]["attached"][1]
    case_topic = fp_topic["children"]["attached"][0]
    assert case_topic["title"] == "正确账号密码登录成功"
    assert case_topic["markers"] == [{"markerId": "priority-1"}]  # P0
    notes = case_topic["notes"]["plain"]["content"]
    assert "前置条件:已注册用户" in notes
    assert "步骤1: 输入账号密码 → 预期: 登录成功" in notes
    assert "执行结果:通过" in notes


def test_export_xmind_project_not_found(client):
    resp = client.get("/api/projects/99999/export/xmind")
    assert resp.status_code == 404


def test_export_xmind_empty_project(client):
    pid = client.post("/api/projects", json={"name": "空导出项目"}).json()["id"]
    resp = client.get(f"/api/projects/{pid}/export/xmind")
    assert resp.status_code == 200
    root = _content(resp)[0]["rootTopic"]
    assert root["title"] == "空导出项目"
    assert "children" not in root
