# 计划10 Task12:脚本列表 scope 筛选 + driver_target 服务端派生落列
from app.database import SessionLocal

V1_WEB = {"version": 1, "meta": {"start_url": "https://x"}, "variables": [],
          "steps": [{"id": "s1", "action": "goto", "params": {"url": "https://x"}}]}
V2_WEB_AI = {"version": 2, "meta": {"target": "web"}, "variables": [],
             "steps": [{"id": "a", "action": "ai_tap", "params": {"target": "按钮"}}]}
V2_ANDROID = {"version": 2, "meta": {"target": "android"}, "variables": [],
              "steps": [{"id": "a", "action": "ai_tap", "params": {"target": "设置"}}]}


def _admin_headers(client):
    from app.bootstrap import ensure_bootstrap_admin
    db = SessionLocal()
    try:
        ensure_bootstrap_admin(db)
    finally:
        db.close()
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _mk_script(client, ah, pid, name, doc):
    return client.post(f"/api/projects/{pid}/ui-scripts", json={"name": name, "script": doc},
                       headers=ah).json()


def test_scope_filters_and_driver_target_derived(client):
    ah = _admin_headers(client)
    pid = client.post("/api/projects", json={"name": "p10scope"}, headers=ah).json()["id"]
    s1 = _mk_script(client, ah, pid, "老Web", V1_WEB)
    s2 = _mk_script(client, ah, pid, "WebAI", V2_WEB_AI)
    s3 = _mk_script(client, ah, pid, "安卓", V2_ANDROID)
    assert s1["driver_target"] == "web" and s3["driver_target"] == "android"  # 派生落列
    all_rows = client.get(f"/api/projects/{pid}/ui-scripts", headers=ah).json()
    assert len(all_rows) == 3
    legacy = client.get(f"/api/projects/{pid}/ui-scripts?scope=web_legacy", headers=ah).json()
    assert [r["name"] for r in legacy] == ["老Web"]
    cross = client.get(f"/api/projects/{pid}/ui-scripts?scope=cross", headers=ah).json()
    assert sorted(r["name"] for r in cross) == ["WebAI", "安卓"]
    assert client.get(f"/api/projects/{pid}/ui-scripts?scope=bogus",
                      headers=ah).status_code == 400
    # 更新派生:安卓脚本改回 web 无 AI 步 → 归入 web_legacy
    upd = client.put(f"/api/ui-scripts/{s3['id']}", json={"name": "安卓改Web", "script": V1_WEB},
                     headers=ah).json()
    assert upd["driver_target"] == "web"
    legacy2 = client.get(f"/api/projects/{pid}/ui-scripts?scope=web_legacy", headers=ah).json()
    assert sorted(r["name"] for r in legacy2) == ["安卓改Web", "老Web"]
