# tests/test_ui_runs_routing.py
"""Task 7:执行分流接线——AI 步/非 web 端走 Node 路径,纯选择器走原 Python 路径;
端锁占用返回 409;快照登录态与 web 端互斥;run_sub 先展开后分流。"""
import time

from app.database import SessionLocal
from app.models import Project, UiRun, UiScript


def _admin_headers(client):
    from app.bootstrap import ensure_bootstrap_admin
    db = SessionLocal()
    try:
        ensure_bootstrap_admin(db)
    finally:
        db.close()
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _mk(client, ah, doc, name="跨端脚本"):
    pid = client.post("/api/projects", json={"name": f"p10r{time.time_ns()}"}, headers=ah).json()["id"]
    sid = client.post(f"/api/projects/{pid}/ui-scripts", json={"name": name, "script": doc},
                      headers=ah).json()["id"]
    return pid, sid


def _wait_terminal(rid: int, timeout: float = 5.0) -> str:
    # 每次轮询新开会话:长持会话在 REPEATABLE READ 下停在旧快照(且 identity map 缓存旧对象),
    # 看不到执行线程的落库,会永远误报 still-running
    dl = time.monotonic() + timeout
    while time.monotonic() < dl:
        db = SessionLocal()
        try:
            r = db.get(UiRun, rid)
            if r is not None and r.status in ("completed", "failed"):
                db.refresh(r)
                return r.status
        finally:
            db.close()
        time.sleep(0.05)
    return "still-running"


AI_DOC = {"version": 2, "meta": {"target": "web", "start_url": "https://x"},
          "variables": [{"name": "username", "default": "admin"}],
          "steps": [{"id": "s1", "action": "ai_input",
                     "params": {"target": "用户名框", "text": "{{username}}"}}]}
SEL_DOC = {"version": 1, "meta": {"start_url": "https://x"}, "variables": [],
           "steps": [{"id": "s1", "action": "goto", "params": {"url": "https://x"}}]}


def test_ai_script_routes_to_node_and_persists_usage(client, monkeypatch):
    ah = _admin_headers(client)
    pid, sid = _mk(client, ah, AI_DOC)
    calls: dict = {}

    def fake_execute(run_id, doc, **kw):
        calls["args"] = (run_id, doc, kw)
        kw["notify"]({"type": "step_end", "index": 0, "step_id": "s1", "action": "ai_input",
                      "status": "passed", "error": None, "screenshot": "step_0_passed.jpg",
                      "elapsed_ms": 5})
        kw["notify"]({"type": "done", "status": "completed",
                      "summary": {"total": 1, "passed": 1, "failed": 0, "duration_ms": 9},
                      "usage": {"input_tokens": 10, "output_tokens": 2},
                      "report_path": "r.html"})
        return {"usage": {"input_tokens": 10}, "report_path": "r.html"}

    monkeypatch.setattr("app.routers.ui_runs.node_runner.execute_ai_run", fake_execute)
    r = client.post(f"/api/projects/{pid}/ui-runs",
                    json={"script_id": sid, "mode": "headless", "variables": {"username": "root"}},
                    headers=ah)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert _wait_terminal(rid) == "completed"
    assert calls["args"][1]["steps"][0]["params"]["text"] == "{{username}}"  # 原文直传(渲染在 Node 侧)
    assert calls["args"][2]["variables"] == {"username": "root"}
    assert calls["args"][2]["driver_target"] == "web"
    db = SessionLocal(); run = db.get(UiRun, rid)
    assert run.driver_target == "web" and run.ai_usage["input_tokens"] == 10
    db.close()


def test_selector_script_keeps_python_path(client, monkeypatch):
    ah = _admin_headers(client)
    pid, sid = _mk(client, ah, SEL_DOC, name="老Web")
    called = {"node": False, "py": False}

    monkeypatch.setattr("app.routers.ui_runs.node_runner.execute_ai_run",
                        lambda *a, **k: called.__setitem__("node", True))
    # 老 Web 脚本会真开浏览器:把 Python 执行器整体短路,只验证「走了这条路径」
    from app.ui_automation import runner as py_runner
    monkeypatch.setattr(py_runner, "execute_script",
                        lambda *a, **k: called.__setitem__("py", True))
    r = client.post(f"/api/projects/{pid}/ui-runs", json={"script_id": sid}, headers=ah)
    assert r.status_code == 201
    rid = r.json()["id"]
    for _ in range(100):
        if called["py"]:
            break
        time.sleep(0.05)
    assert called["py"] is True and called["node"] is False


def test_android_busy_returns_409_with_target_lock(client, monkeypatch):
    from app.ui_automation import nodepath
    ah = _admin_headers(client)
    pid, sid = _mk(client, ah, {**AI_DOC, "meta": {"target": "android"}})
    nodepath.TARGET_LOCKS["android"].acquire()
    try:
        r = client.post(f"/api/projects/{pid}/ui-runs", json={"script_id": sid}, headers=ah)
        assert r.status_code == 409
        assert "android" in r.json()["detail"]
    finally:
        nodepath.TARGET_LOCKS["android"].release()


def test_snapshot_on_web_target_rejected(client):
    ah = _admin_headers(client)
    pid, sid = _mk(client, ah, AI_DOC)
    db = SessionLocal()
    from app.models import UiAuthState
    a = UiAuthState(project_id=pid, name="快照", storage_path="x.tar",
                    kind="android_snapshot", app_package="com.demo.app")
    db.add(a); db.commit(); aid = a.id; db.close()
    r = client.post(f"/api/projects/{pid}/ui-runs",
                    json={"script_id": sid, "auth_state_id": aid}, headers=ah)
    assert r.status_code == 400


def test_run_sub_expands_before_routing(client, monkeypatch):
    ah = _admin_headers(client)
    pid = client.post("/api/projects", json={"name": f"p10sub{time.time_ns()}"}, headers=ah).json()["id"]
    sub_id = client.post(f"/api/projects/{pid}/ui-scripts", json={"name": "登录子脚本", "script": {
        "version": 2, "meta": {"target": "web"}, "variables": [],
        "steps": [{"id": "L1", "action": "ai_tap", "params": {"target": "登录入口"}}]},
    }, headers=ah).json()["id"]
    main_id = client.post(f"/api/projects/{pid}/ui-scripts", json={"name": "主脚本", "script": {
        "version": 2, "meta": {"target": "web"}, "variables": [],
        "steps": [{"id": "M1", "action": "run_sub", "params": {"script_id": sub_id}},
                  {"id": "M2", "action": "ai_assert", "params": {"assertion": "已登录"}}]},
    }, headers=ah).json()["id"]
    captured: dict = {}

    def fake_execute(run_id, doc, **kw):
        captured["steps"] = doc["steps"]
        kw["notify"]({"type": "done", "status": "completed",
                      "summary": {"total": 2, "passed": 2, "failed": 0, "duration_ms": 5}})
        return {}

    monkeypatch.setattr("app.routers.ui_runs.node_runner.execute_ai_run", fake_execute)
    r = client.post(f"/api/projects/{pid}/ui-runs", json={"script_id": main_id}, headers=ah)
    assert r.status_code == 201
    _wait_terminal(r.json()["id"])
    assert [s["id"] for s in captured["steps"]] == ["L1", "M2"]
