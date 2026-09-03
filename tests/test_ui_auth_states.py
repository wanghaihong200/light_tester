# tests/test_ui_auth_states.py
"""登录态管理测试:HTTP 只打 404/400/409/软删等便宜分支(不真开浏览器会话);
storage_state 加载走 runner 集成链路(headless 真开 chromium,补 Task 4 未实测的分支)。"""
import itertools
import time

import pytest

from app.jobs.bus import JobEventBus
from app.models import Project, UiAuthState, UiRun, UiScript
from app.ui_automation import runner
from app.ui_automation.recorder import RecordingSession
from app.ui_automation.session import INTERACTIVE_SLOT

_names = itertools.count(1)


def _mk_project() -> int:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        p = Project(name=f"auth-p{next(_names)}")
        db.add(p); db.commit()
        return p.id
    finally:
        db.close()


def _mk_auth(project_id: int, storage_path: str) -> int:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        row = UiAuthState(project_id=project_id, name="n", storage_path=storage_path)
        db.add(row); db.commit()
        return row.id
    finally:
        db.close()


def _mk_script_run(project_id: int) -> int:
    """造 UiRun 行(执行器落库需要);脚本文档由用例直接传,不走脚本内容。"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        s = UiScript(project_id=project_id, name="s",
                     script={"version": 1, "meta": {}, "variables": [], "steps": []})
        db.add(s); db.flush()
        r = UiRun(project_id=project_id, script_id=s.id, script_name="s", mode="headless")
        db.add(r); db.commit()
        return r.id
    finally:
        db.close()


def _get_run(run_id: int) -> UiRun:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        return db.get(UiRun, run_id)
    finally:
        db.close()


def test_auth_state_api_guards_without_browser(client):
    """便宜分支全量:路由注册、项目404、会话404、槽位409、空列表;全程不真开浏览器。"""
    spec = client.get("/openapi.json").json()["paths"]
    for p in ("/api/projects/{project_id}/ui-auth-states/collect",
              "/api/ui-auth-collect/{cid}/save", "/api/ui-auth-collect/{cid}/cancel",
              "/api/projects/{project_id}/ui-auth-states", "/api/ui-auth-states/{auth_id}"):
        assert p in spec, p
    pid = _mk_project()
    assert client.get(f"/api/projects/{pid}/ui-auth-states").json() == []
    # 项目不存在:先于开会话返回 404
    assert client.post("/api/projects/9999/ui-auth-states/collect",
                       json={"name": "管理员"}).status_code == 404
    assert client.post("/api/ui-auth-collect/9999/save").status_code == 404
    assert client.post("/api/ui-auth-collect/9999/cancel").status_code == 404
    for _ in range(100):  # 预占全局槽位(等先前会话释放),collect 因此走 409 而非真开浏览器
        if INTERACTIVE_SLOT.acquire(blocking=False):
            break
        time.sleep(0.1)
    else:
        pytest.fail("INTERACTIVE_SLOT 被先前会话占住,无法预占")
    try:
        r = client.post(f"/api/projects/{pid}/ui-auth-states/collect", json={"name": "管理员"})
        assert r.status_code == 409
        assert "会话" in r.json()["detail"]
    finally:
        INTERACTIVE_SLOT.release()


def test_auth_state_list_and_soft_delete(client, tmp_path):
    """列表可见 → 软删后列表消失、文件一并清、二次删除 404(软删行保留审计痕迹)。"""
    pid = _mk_project()
    f = tmp_path / "999.json"
    f.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    aid = _mk_auth(pid, str(f))
    rows = client.get(f"/api/projects/{pid}/ui-auth-states").json()
    assert [r["id"] for r in rows] == [aid]
    assert set(rows[0]) == {"id", "project_id", "name", "created_at"}  # 路径/软删标记不外泄
    assert client.delete(f"/api/ui-auth-states/{aid}").status_code == 204
    assert not f.exists()
    assert client.delete(f"/api/ui-auth-states/{aid}").status_code == 404
    assert client.get(f"/api/projects/{pid}/ui-auth-states").json() == []
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        assert db.get(UiAuthState, aid).is_deleted is True
    finally:
        db.close()


def test_run_rejects_invalid_auth_state_id(client):
    """ui_runs 的 auth_state_id 校验:不存在/跨项目/软删 一律 400(在占执行锁之前拒掉)。"""
    pid_a, pid_b = _mk_project(), _mk_project()
    aid = _mk_auth(pid_a, "auth/none.json")
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        s = UiScript(project_id=pid_b, name="s",
                     script={"version": 1, "meta": {}, "variables": [], "steps": []})
        db.add(s); db.commit(); sid = s.id
    finally:
        db.close()
    assert client.post(f"/api/projects/{pid_b}/ui-runs",
                       json={"script_id": sid, "auth_state_id": 99999}).status_code == 400
    # 跨项目引用:登录态属于 pid_a,在 pid_b 下使用必须 400
    assert client.post(f"/api/projects/{pid_b}/ui-runs",
                       json={"script_id": sid, "auth_state_id": aid}).status_code == 400
    # 软删后不可再引用
    assert client.delete(f"/api/ui-auth-states/{aid}").status_code == 204
    assert client.post(f"/api/projects/{pid_b}/ui-runs",
                       json={"script_id": sid, "auth_state_id": aid}).status_code == 400


def test_execute_script_loads_storage_state(tmp_path):
    """合法 storage_state 文件 → context 带登录态启动并跑完(Task 4 只测过 None 分支)。"""
    state = tmp_path / "state.json"
    state.write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    run_id = _mk_script_run(_mk_project())
    doc = {"version": 1, "meta": {}, "variables": [],
           "steps": [{"id": "s1", "action": "goto",
                      "params": {"url": "data:text/html,<html><title>t</title></html>"}}]}
    runner.execute_script(run_id, doc, mode="headless", variables={},
                          auth_state_path=str(state), data_dir=tmp_path,
                          notify=lambda e: None)
    r = _get_run(run_id)
    assert r.status == "completed" and r.steps_total == 1 and r.steps_failed == 0


def test_execute_script_missing_storage_state_env_failed(tmp_path):
    """storage_state 路径不存在 → context 建不起来,按环境级 failed 落库并发 error 事件。"""
    run_id = _mk_script_run(_mk_project())
    doc = {"version": 1, "meta": {}, "variables": [],
           "steps": [{"id": "s1", "action": "goto", "params": {"url": "about:blank"}}]}
    events = []
    runner.execute_script(run_id, doc, mode="headless", variables={},
                          auth_state_path=str(tmp_path / "nope.json"), data_dir=tmp_path,
                          notify=events.append)
    assert any(e["type"] == "error" for e in events)
    r = _get_run(run_id)
    assert r.status == "failed" and r.steps_passed == 0 and r.steps_failed == 0
    assert r.error  # 环境级错误信息落库,而非步骤失败


def test_recorder_emits_stopped_even_if_close_cb_raises():
    """注销回调抛异常时 stopped 仍必发(Task 5 re-review 建议,前端靠它结束 SSE 流);
    异常本身照旧向上抛,由会话线程收尾兜底。"""
    events = []
    s = RecordingSession.__new__(RecordingSession)  # 跳过 __init__(其会自动开会话)
    s.recording_id = 1
    s.on_event = events.append
    s._bus = JobEventBus()  # 无订阅者,投递即空操作(单测不起主循环)
    s._close_cb = lambda: 1 / 0  # 模拟注销回调异常
    with pytest.raises(ZeroDivisionError):
        s._on_close()
    assert [e["type"] for e in events] == ["stopped"]
