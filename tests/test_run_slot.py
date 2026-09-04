# tests/test_run_slot.py
"""Task 12:RUN_SLOT 信号量化(可配置 5 槽)。
容量来自 settings.run_slot_count(默认 5);ui_runs.py 以 runner.RUN_SLOT 属性方式访问,
monkeypatch runner 模块属性即真实生效,占满槽后下一执行请求 409 且文案含「执行槽」。
注:简报样例的 UiScriptSave 字段(script_name/mode/doc)与真实契约不符(app/schemas.py
真实必填为 name + script),ui-runs 真实路由为 /api/projects/{pid}/ui-runs,已按代码对齐。"""
import threading


def test_slot_capacity_from_settings():
    from app.ui_automation import runner
    from app.config import settings
    assert runner.RUN_SLOT._initial_value == settings.run_slot_count  # BoundedSemaphore 内部字段


def test_slot_exhaustion_409(client, db_session, make_user, monkeypatch):
    """占满槽后下一个执行请求 409——脚本/项目先建好,monkeypatch RUN_SLOT 为容量1的信号量以简化占位。"""
    from app.ui_automation import runner
    monkeypatch.setattr(runner, "RUN_SLOT", threading.BoundedSemaphore(1))
    runner.RUN_SLOT.acquire(blocking=False)  # 占住唯一槽
    from app.bootstrap import ensure_bootstrap_admin
    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    ah = {"Authorization": f"Bearer {atok}"}
    pid = client.post("/api/projects", json={"name": "slot"}, headers=ah).json()["id"]
    sid = client.post(f"/api/projects/{pid}/ui-scripts",
                      json={"name": "s", "script": {"version": 1, "meta": {}, "variables": [], "steps": []}},
                      headers=ah).json()["id"]
    r = client.post(f"/api/projects/{pid}/ui-runs", json={"script_id": sid, "mode": "headless"}, headers=ah)
    assert r.status_code == 409 and "执行槽" in r.json()["detail"]
