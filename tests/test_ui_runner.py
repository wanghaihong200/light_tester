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
    """长步骤(wait 2.5s)期间心跳帧必须持续推送:预览流不能只在步骤边界发帧。
    只统计 step_index==1(wait 步骤期间)的帧:边界帧凑不了数,间隔调大即红。"""
    db, p, s = owned
    doc = {"version": 1, "meta": {}, "variables": [],
           "steps": [{"id": "s1", "action": "goto", "params": {"url": page_file}},
                     {"id": "s2", "action": "wait", "params": {"ms": 2500}}]}
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, mode="headless")
    db.add(run); db.commit()
    events = []
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=events.append)
    frames = [e for e in events if e["type"] == "frame" and e.get("step_index") == 1]
    # 2.5s / 0.6s ≈ 4 次心跳 + 1 帧步骤边界帧,健康值约 5;仅边界发帧时只有 1 帧
    assert len(frames) >= 3, f"wait 期间心跳帧不足: {len(frames)}"


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


def test_run_api_409_when_slot_occupied(client, owned):
    """全局并发=1:锁被占用时创建必须 409,且不得落库(无 pending 僵尸 run)。"""
    db, p, s = owned
    doc = {"version": 1, "meta": {}, "variables": [],
           "steps": [{"id": "s1", "action": "wait", "params": {"ms": 50}}]}
    from app.database import SessionLocal
    db2 = SessionLocal(); row = db2.get(UiScript, s.id); row.script = doc; db2.commit(); db2.close()
    for _ in range(100):  # 等上一用例的执行线程释放锁后再预占(0.1s 间隔,上限 10s)
        if runner.RUN_SLOT.acquire(blocking=False):
            break
        time.sleep(0.1)
    else:
        pytest.fail("RUN_SLOT 被先前用例占住,无法预占")
    try:
        for _ in range(2):  # 连续两次都 409:守卫不被单次请求消费
            r = client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id})
            assert r.status_code == 409
            assert "已有执行" in r.json()["detail"]
        db3 = SessionLocal()
        try:
            assert db3.query(UiRun).filter(UiRun.project_id == p.id).count() == 0
        finally:
            db3.close()
    finally:
        runner.RUN_SLOT.release()
    # 释放后可正常创建(锁的所有权移交线程),并等它跑完避免弄脏下一用例
    r = client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id})
    assert r.status_code == 201
    for _ in range(100):
        if client.get(f"/api/ui-runs/{r.json()['id']}").json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.3)


def test_run_screenshot_name_guard(client):
    """截图文件名守卫:目录名/非 .jpg 名 400(先于存在性检查),合法名但无文件 404。
    注:裸 `..`/`.` 会被 httpx 客户端在发出前规范化(到不了路由),故用 %2e 编码形态打守卫。"""
    assert client.get("/api/ui-runs/999999/screens/%2e%2e").status_code == 400
    assert client.get("/api/ui-runs/999999/screens/.%2e").status_code == 400
    assert client.get("/api/ui-runs/999999/screens/step_0_passed.png").status_code == 400
    assert client.get("/api/ui-runs/999999/screens/..%5capp%5cmain.py").status_code == 400
    assert client.get("/api/ui-runs/999999/screens/step_0_passed.jpg").status_code == 404


def test_assert_contains_whitespace_normalized(tmp_path, owned):
    """E2E:元素文本含换行/连续空格时 contains 不背刺(dsl.text_matches 归一化接线)。
    背景冒烟:页面文本「AI 测试」断言「AI测试」误判为 equals——归一化语义见用户拍板 2026-09-03(仅坍缩)。"""
    db, p, s = owned
    html = '<html><body><div id="t">线条\n  之间的   空白</div></body></html>'
    f = tmp_path / "ws.html"
    f.write_text(html, encoding="utf-8")
    doc = {"version": 1, "meta": {}, "variables": [], "steps": [
        {"id": "s1", "action": "goto", "params": {"url": f.as_uri()}},
        {"id": "s2", "action": "assert_text", "locator": {"strategy": "css", "value": "#t"},
         "params": {"text": "线条 之间的 空白", "mode": "contains"}}]}
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, mode="headless")
    db.add(run); db.commit()
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=lambda e: None)
    from app.database import SessionLocal
    db2 = SessionLocal(); r = db2.get(UiRun, run.id)
    assert r.status == "completed" and r.steps_failed == 0
    db2.close()


def test_assert_fail_error_includes_mode(tmp_path, page_file, owned):
    """断言失败报错必须标明 mode:历史里「文本不匹配: 期望[..] 实际[..]」两种模式长得一样,
    用户曾据历史把 contains 误判成 equals(2026-09-03 脚本10案例)。"""
    db, p, s = owned
    doc = _doc(page_file)  # 第4步 assert_text mode=equals
    doc["steps"][3]["params"]["text"] = "不会出现的文本"
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, mode="headless")
    db.add(run); db.commit()
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=lambda e: None)
    from app.database import SessionLocal
    db2 = SessionLocal(); r = db2.get(UiRun, run.id)
    assert r.status == "failed"
    assert "文本不匹配(equals)" in (r.step_results[3]["error"] or "")
    db2.close()


def test_scroll_step_executes(tmp_path, owned):
    """scroll 步骤真实滚动主文档:页面 onscroll 把「scrolled」写进 #out,断言随之通过(需求2)。"""
    db, p, s = owned
    html = ('<html><body style="margin:0"><div style="height:3000px">long</div>'
            '<div id="out">top</div>'
            '<script>window.addEventListener("scroll",()=>{'
            'if(window.scrollY>100)document.getElementById("out").textContent="scrolled";});</script>'
            '</body></html>')
    f = tmp_path / "long.html"
    f.write_text(html, encoding="utf-8")
    doc = {"version": 1, "meta": {}, "variables": [], "steps": [
        {"id": "s1", "action": "goto", "params": {"url": f.as_uri()}},
        {"id": "s2", "action": "scroll", "params": {"dx": 0, "dy": 600}},
        {"id": "s3", "action": "assert_text", "locator": {"strategy": "css", "value": "#out"},
         "params": {"text": "scrolled", "mode": "equals"}}]}
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, mode="headless")
    db.add(run); db.commit()
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=lambda e: None)
    from app.database import SessionLocal
    db2 = SessionLocal(); r = db2.get(UiRun, run.id)
    assert r.status == "completed", (r.error, [x["error"] for x in r.step_results if x["error"]])
    db2.close()


def test_click_screenshot_has_cursor_mark(tmp_path, page_file, owned):
    """执行截图点击标示(需求1):click 步骤的存档截图上必须出现红色光标/圆环像素。"""
    from io import BytesIO
    from PIL import Image
    db, p, s = owned
    doc = {"version": 1, "meta": {}, "variables": [], "steps": [
        {"id": "s1", "action": "goto", "params": {"url": page_file}},
        {"id": "s2", "action": "click", "locator": {"strategy": "css", "value": "#go"}}]}
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, mode="headless")
    db.add(run); db.commit()
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=lambda e: None)
    from app.database import SessionLocal
    db2 = SessionLocal(); r = db2.get(UiRun, run.id)
    assert r.status == "completed" and r.step_results[1]["status"] == "passed"
    db2.close()
    shot = (tmp_path / "runs" / str(run.id) / "step_1_passed.jpg").read_bytes()
    img = Image.open(BytesIO(shot)).convert("RGB")
    reds = sum(1 for px in img.getdata() if px[0] > 200 and px[1] < 140 and px[2] < 140)
    assert reds > 30, f"click 截图未见红色标示,红色像素数={reds}"


# ── 强制结束(2026-09-04 需求:异常挂起时可手动收口,状态置「执行异常」)──────────


def test_force_finish_api_paths(client, owned):
    """404(不存在)/ 400(已终态)/ 200(running→failed,error 带文案,终态时间落库)。"""
    db, p, s = owned
    assert client.post("/api/ui-runs/999999/force-finish").status_code == 404
    r = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, status="completed")
    db.add(r); db.commit()
    assert client.post(f"/api/ui-runs/{r.id}/force-finish").status_code == 400
    r2 = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, status="running")
    db.add(r2); db.commit()
    resp = client.post(f"/api/ui-runs/{r2.id}/force-finish")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed" and "强制结束" in body["error"] and body["finished_at"]


def test_force_finish_cancels_thread_and_guards_state(client, tmp_path, owned):
    """E2E:执行中强制结束 → 线程在步骤边界退出释放 RUN_SLOT;迟到的完成落库不翻案。"""
    import time as _t
    db, p, s = owned
    url = "data:text/html,<html><title>t</title></html>"
    doc = {"version": 1, "meta": {}, "variables": [], "steps": [
        {"id": "s1", "action": "goto", "params": {"url": url}},
        {"id": "s2", "action": "wait", "params": {"ms": 1500}},
        {"id": "s3", "action": "wait", "params": {"ms": 1500}}]}
    from app.database import SessionLocal
    db2 = SessionLocal(); row = db2.get(UiScript, s.id); row.script = doc; db2.commit(); db2.close()
    resp = client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id})
    assert resp.status_code == 201
    run_id = resp.json()["id"]
    for _ in range(50):  # 等 run 真正进入执行(约第 2 步时动手)
        if client.get(f"/api/ui-runs/{run_id}").json()["status"] == "running":
            break
        _t.sleep(0.2)
    _t.sleep(1.8)  # 落在第 2~3 步之间
    assert client.post(f"/api/ui-runs/{run_id}/force-finish").status_code == 200
    for _ in range(100):  # 线程在步骤边界自杀后槽必须释放(上限 20s)
        if runner.RUN_SLOT.acquire(blocking=False):
            runner.RUN_SLOT.release()
            break
        _t.sleep(0.2)
    else:
        pytest.fail("强制结束后执行线程未退出,RUN_SLOT 未释放")
    st = client.get(f"/api/ui-runs/{run_id}").json()
    assert st["status"] == "failed" and "强制结束" in st["error"]  # 迟到落库未翻案
