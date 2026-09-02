# UI自动化脚本 CRUD API 测试:创建/列表/详情/更新/软删 + 项目隔离
def _mk_project(client, name="ui-crud-p"):
    return client.post("/api/projects", json={"name": name}).json()


DOC = {"version": 1, "meta": {"start_url": "https://x.com"}, "variables": [], "steps": []}


def test_script_crud_roundtrip(client):
    pid = _mk_project(client)["id"]
    r = client.post(f"/api/projects/{pid}/ui-scripts", json={"name": "登录", "script": DOC})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["script"]["version"] == 1

    lst = client.get(f"/api/projects/{pid}/ui-scripts").json()
    assert [s["id"] for s in lst] == [sid]

    up = client.put(f"/api/ui-scripts/{sid}", json={"name": "登录2", "description": "d", "script": DOC})
    assert up.status_code == 200 and up.json()["name"] == "登录2"

    assert client.delete(f"/api/ui-scripts/{sid}").status_code == 204
    assert client.get(f"/api/ui-scripts/{sid}").status_code == 404  # 软删后视为不存在


def test_script_project_isolation_and_404(client):
    p1 = _mk_project(client, "p1")
    p2 = _mk_project(client, "p2")
    sid = client.post(f"/api/projects/{p1['id']}/ui-scripts", json={"name": "a", "script": DOC}).json()["id"]
    assert client.get(f"/api/ui-scripts/{sid}").json()["project_id"] == p1["id"]
    assert client.put(f"/api/ui-scripts/{sid}", json={"name": "b", "script": DOC}).status_code == 200
    assert client.post("/api/projects/99999/ui-scripts", json={"name": "x", "script": DOC}).status_code == 404
