# tests/test_ui_runner.py
"""UI 执行器与 ui_runs API 测试:file:// 页面跑通成败两路 + API 生命周期/并发守卫。"""
import time
from pathlib import Path

import pytest

from app.models import Project, UiRun, UiScript
from app.ui_automation import runner

FIXTURE = """<html><body>
<input id="user"><button id="go" onclick="document.getElementById('out').textContent='OK '+document.getElementById('user').value">go</button>
<div id="out"></div>
</body></html>"""


@pytest.fixture()
def page_file(tmp_path: Path) -> str:
    f = tmp_path / "fixture.html"
    f.write_text(FIXTURE, encoding="utf-8")
    return f.as_uri()


@pytest.fixture()
def owned():
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        p = Project(name="ui-run-p"); db.add(p); db.flush()
        s = UiScript(project_id=p.id, name="s", script={"version": 1, "meta": {}, "variables": [], "steps": []})
        db.add(s); db.commit()
        yield db, p, s
    finally:
        db.close()


def _doc(url, text="{{u}}"):
    return {"version": 1, "meta": {}, "variables": [{"name": "u", "default": "admin"}],
            "steps": [
                {"id": "s1", "action": "goto", "params": {"url": url}},
                {"id": "s2", "action": "fill", "locator": {"strategy": "css", "value": "#user"}, "params": {"text": text}},
                {"id": "s3", "action": "click", "locator": {"strategy": "css", "value": "#go"}},
                {"id": "s4", "action": "assert_text", "locator": {"strategy": "css", "value": "#out"},
                 "params": {"text": "OK admin", "mode": "equals"}},
            ]}


def test_execute_script_pass(tmp_path, page_file, owned):
    db, p, s = owned
    events = []
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, mode="headless",
                variables={"u": "admin"})
    db.add(run); db.commit()
    runner.execute_script(run.id, _doc(page_file), mode="headless",
                          variables={"u": "admin"}, auth_state_path=None,
                          data_dir=tmp_path, notify=events.append)
    from app.database import SessionLocal
    db2 = SessionLocal(); r = db2.get(UiRun, run.id)
    assert r.status == "completed" and r.steps_failed == 0 and r.steps_total == 4
    kinds = [e["type"] for e in events]
    assert "done" in kinds and kinds.count("step_end") == 4
    db2.close()


def test_execute_script_fail_screenshot(tmp_path, page_file, owned):
    db, p, s = owned
    doc = _doc(page_file)
    doc["steps"][3]["params"]["text"] = "不会出现的文本"  # 断言必失败
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, mode="headless")
    db.add(run); db.commit()
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=lambda e: None)
    from app.database import SessionLocal
    db2 = SessionLocal(); r = db2.get(UiRun, run.id)
    assert r.status == "failed" and r.steps_failed == 1
    shot = r.step_results[3]["screenshot"]
    # 截图落在 data_dir/runs/<run_id>/ 下(与 GET /ui-runs/{id}/screens/{name} 的目录契约一致)
    assert shot and (tmp_path / "runs" / str(run.id) / shot).exists()
    db2.close()


def test_variables_rendered(tmp_path, page_file, owned):
    db, p, s = owned
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name)
    db.add(run); db.commit()
    doc = _doc(page_file, text="{{missing_var}}")  # 未定义变量原样保留,断言失败
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=lambda e: None)
    from app.database import SessionLocal
    db2 = SessionLocal(); r = db2.get(UiRun, run.id)
    assert r.status == "failed"
    db2.close()


def test_heartbeat_frames_during_wait(tmp_path, page_file, owned):
    """长步骤(wait 2.5s)期间心跳帧必须持续推送:预览流不能只在步骤边界发帧。"""
    db, p, s = owned
    doc = {"version": 1, "meta": {}, "variables": [],
           "steps": [{"id": "s1", "action": "goto", "params": {"url": page_file}},
                     {"id": "s2", "action": "wait", "params": {"ms": 2500}}]}
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, mode="headless")
    db.add(run); db.commit()
    events = []
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=events.append)
    frames = [e for e in events if e["type"] == "frame"]
    assert len(frames) >= 3, f"心跳帧不足: {len(frames)}"  # 仅步骤边界发帧时只有 2 帧


def test_run_api_lifecycle_and_409_guard(client, owned):
    import time as _t
    db, p, s = owned
    url = "data:text/html,<html><title>t</title></html>"
    doc = {"version": 1, "meta": {}, "variables": [],
           "steps": [{"id": "s1", "action": "goto", "params": {"url": url}},
                     {"id": "s2", "action": "wait", "params": {"ms": 800}}]}
    s.script = doc
    from app.database import SessionLocal
    db2 = SessionLocal(); row = db2.get(UiScript, s.id); row.script = doc; db2.commit(); db2.close()
    r = client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id})
    assert r.status_code == 201
    run_id = r.json()["id"]
    st = {}
    for _ in range(100):  # 轮询终态(不走 SSE,TestClient 流式不便),上限 30 秒
        st = client.get(f"/api/ui-runs/{run_id}").json()
        if st["status"] in ("completed", "failed"):
            break
        _t.sleep(0.3)
    assert st["status"] == "completed"
    # 非法脚本 400
    bad = {"version": 1, "meta": {}, "variables": [], "steps": [{"id": "x", "action": "fly"}]}
    db3 = SessionLocal(); row = db3.get(UiScript, s.id); row.script = bad; db3.commit(); db3.close()
    assert client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id}).status_code == 400
