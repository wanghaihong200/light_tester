# tests/test_ui_runner.py
"""UI 执行器与 ui_runs API 测试:file:// 页面跑通成败两路 + API 生命周期/并发守卫。
Task 8 补鉴权:业务端点全量 401 后,走 API 的用例统一带 admin 头(保语义,补鉴权)。"""
import time
from pathlib import Path

import pytest

from app.models import Project, UiRun, UiScript
from app.ui_automation import runner


def _admin_headers(client):
    from app.bootstrap import ensure_bootstrap_admin
    from app.database import SessionLocal as SL

    db = SL()
    try:
        ensure_bootstrap_admin(db)
    finally:
        db.close()
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}

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


def _fresh_run(run_id: int) -> UiRun:
    """新会话读 run(断言失败也不泄漏事务:泄漏会让下一个用例的 TRUNCATE 等元数据锁)。"""
    from contextlib import closing
    from app.database import SessionLocal

    with closing(SessionLocal()) as db2:
        return db2.get(UiRun, run_id)


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
    r = _fresh_run(run.id)
    assert r.status == "completed" and r.steps_failed == 0 and r.steps_total == 4
    kinds = [e["type"] for e in events]
    assert "done" in kinds and kinds.count("step_end") == 4


def test_execute_script_fail_screenshot(tmp_path, page_file, owned):
    db, p, s = owned
    doc = _doc(page_file)
    doc["steps"][3]["params"]["text"] = "不会出现的文本"  # 断言必失败
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, mode="headless")
    db.add(run); db.commit()
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=lambda e: None)
    r = _fresh_run(run.id)
    assert r.status == "failed" and r.steps_failed == 1
    shot = r.step_results[3]["screenshot"]
    # 截图落在 data_dir/runs/<run_id>/ 下(与 GET /ui-runs/{id}/screens/{name} 的目录契约一致)
    assert shot and (tmp_path / "runs" / str(run.id) / shot).exists()


def test_variables_rendered(tmp_path, page_file, owned):
    db, p, s = owned
    run = UiRun(project_id=p.id, script_id=s.id, script_name=s.name)
    db.add(run); db.commit()
    doc = _doc(page_file, text="{{missing_var}}")  # 未定义变量原样保留,断言失败
    runner.execute_script(run.id, doc, mode="headless", variables={},
                          auth_state_path=None, data_dir=tmp_path, notify=lambda e: None)
    r = _fresh_run(run.id)
    assert r.status == "failed"


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
    _fresh_run(run.id)  # 见 _fresh_run:断言失败不得泄漏事务


def test_run_api_lifecycle_and_409_guard(client, owned):
    import time as _t
    db, p, s = owned
    ah = _admin_headers(client)
    url = "data:text/html,<html><title>t</title></html>"
    doc = {"version": 1, "meta": {}, "variables": [],
           "steps": [{"id": "s1", "action": "goto", "params": {"url": url}},
                     {"id": "s2", "action": "wait", "params": {"ms": 800}}]}
    s.script = doc
    from app.database import SessionLocal
    db2 = SessionLocal(); row = db2.get(UiScript, s.id); row.script = doc; db2.commit(); db2.close()
    r = client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id}, headers=ah)
    assert r.status_code == 201
    run_id = r.json()["id"]
    st = {}
    for _ in range(100):  # 轮询终态(不走 SSE,TestClient 流式不便),上限 30 秒
        st = client.get(f"/api/ui-runs/{run_id}", headers=ah).json()
        if st["status"] in ("completed", "failed"):
            break
        _t.sleep(0.3)
    assert st["status"] == "completed"
    # 非法脚本 400
    bad = {"version": 1, "meta": {}, "variables": [], "steps": [{"id": "x", "action": "fly"}]}
    db3 = SessionLocal(); row = db3.get(UiScript, s.id); row.script = bad; db3.commit(); db3.close()
    assert client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id}, headers=ah).status_code == 400


def test_run_api_409_when_slot_occupied(client, owned):
    """执行槽占满时创建必须 409(Task 12 后容量来自 settings.run_slot_count),且不得落库(无 pending 僵尸 run)。"""
    db, p, s = owned
    ah = _admin_headers(client)
    doc = {"version": 1, "meta": {}, "variables": [],
           "steps": [{"id": "s1", "action": "wait", "params": {"ms": 50}}]}
    from app.database import SessionLocal
    db2 = SessionLocal(); row = db2.get(UiScript, s.id); row.script = doc; db2.commit(); db2.close()
    held = 0
    for _ in range(100):  # 占满全部执行槽(容量来自 settings.run_slot_count);先前用例线程未让位则等(0.1s 间隔,上限 10s)
        while runner.RUN_SLOT.acquire(blocking=False):
            held += 1
        if held:
            break
        time.sleep(0.1)
    else:
        pytest.fail("RUN_SLOT 被先前用例占住,无法预占")
    try:
        for _ in range(2):  # 连续两次都 409:守卫不被单次请求消费
            r = client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id}, headers=ah)
            assert r.status_code == 409
            assert "执行槽" in r.json()["detail"]  # Task 12 文案:「执行槽已满(上限 N),请稍后重试」
        db3 = SessionLocal()
        try:
            assert db3.query(UiRun).filter(UiRun.project_id == p.id).count() == 0
        finally:
            db3.close()
    finally:
        for _ in range(held):  # 只归还自己占到的槽(BoundedSemaphore 超额 release 会 ValueError)
            runner.RUN_SLOT.release()
    # 释放后可正常创建(锁的所有权移交线程),并等它跑完避免弄脏下一用例
    r = client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id}, headers=ah)
    assert r.status_code == 201
    for _ in range(100):
        if client.get(f"/api/ui-runs/{r.json()['id']}", headers=ah).json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.3)


def test_run_screenshot_name_guard(client):
    """截图文件名守卫:目录名/非 .jpg 名 400(先于存在性检查),合法名但无文件 404。
    注:裸 `..`/`.` 会被 httpx 客户端在发出前规范化(到不了路由),故用 %2e 编码形态打守卫。
    Task 8:400 便宜守卫仍先于闸门;run 不存在 → 404 先于文件检查;无头 → 401。"""
    ah = _admin_headers(client)
    assert client.get("/api/ui-runs/999999/screens/%2e%2e", headers=ah).status_code == 400
    assert client.get("/api/ui-runs/999999/screens/.%2e", headers=ah).status_code == 400
    assert client.get("/api/ui-runs/999999/screens/step_0_passed.png", headers=ah).status_code == 400
    assert client.get("/api/ui-runs/999999/screens/..%5capp%5cmain.py", headers=ah).status_code == 400
    assert client.get("/api/ui-runs/999999/screens/step_0_passed.jpg", headers=ah).status_code == 404
    assert client.get("/api/ui-runs/999999/screens/step_0_passed.jpg").status_code == 401


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
    r = _fresh_run(run.id)
    assert r.status == "completed" and r.steps_failed == 0


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
    r = _fresh_run(run.id)
    assert r.status == "failed"
    assert "文本不匹配(equals)" in (r.step_results[3]["error"] or "")


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
    r = _fresh_run(run.id)
    assert r.status == "completed", (r.error, [x["error"] for x in r.step_results if x["error"]])


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
    r = _fresh_run(run.id)
    assert r.status == "completed" and r.step_results[1]["status"] == "passed"
    shot = (tmp_path / "runs" / str(run.id) / "step_1_passed.jpg").read_bytes()
    img = Image.open(BytesIO(shot)).convert("RGB")
    reds = sum(1 for px in img.getdata() if px[0] > 200 and px[1] < 140 and px[2] < 140)
    assert reds > 30, f"click 截图未见红色标示,红色像素数={reds}"


# ── 强制结束(2026-09-04 需求:异常挂起时可手动收口,状态置「执行异常」)──────────


def test_force_finished_flag_is_one_shot():
    """强制结束标记一次性消费:同一 id 复用时不得被旧标记误杀。
    回归背景:测试库 TRUNCATE 复位自增,残留标记曾让后续用例的 run 第一步即
    ForceCancelled 静默放行(状态永远停在 running、0 帧),且只有全量跑才暴露。"""
    runner.mark_force_finished(424242)
    assert runner.is_force_finished(424242) is True   # 命中即消费
    assert runner.is_force_finished(424242) is False  # 第二次已是干净 id
    assert runner.is_force_finished(424243) is False  # 未标记的 id 不受影响


def test_force_finish_api_paths(client, owned):
    """404(不存在)/ 400(已终态)/ 200(running→failed,error 带文案,终态时间落库)。"""
    db, p, s = owned
    ah = _admin_headers(client)
    assert client.post("/api/ui-runs/999999/force-finish", headers=ah).status_code == 404
    r = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, status="completed")
    db.add(r); db.commit()
    assert client.post(f"/api/ui-runs/{r.id}/force-finish", headers=ah).status_code == 400
    r2 = UiRun(project_id=p.id, script_id=s.id, script_name=s.name, status="running")
    db.add(r2); db.commit()
    resp = client.post(f"/api/ui-runs/{r2.id}/force-finish", headers=ah)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed" and "强制结束" in body["error"] and body["finished_at"]


def test_force_finish_cancels_thread_and_guards_state(client, tmp_path, owned):
    """E2E:执行中强制结束 → 线程在步骤边界退出释放 RUN_SLOT;迟到的完成落库不翻案。"""
    import time as _t
    db, p, s = owned
    ah = _admin_headers(client)
    url = "data:text/html,<html><title>t</title></html>"
    doc = {"version": 1, "meta": {}, "variables": [], "steps": [
        {"id": "s1", "action": "goto", "params": {"url": url}},
        {"id": "s2", "action": "wait", "params": {"ms": 1500}},
        {"id": "s3", "action": "wait", "params": {"ms": 1500}}]}
    from app.database import SessionLocal
    db2 = SessionLocal(); row = db2.get(UiScript, s.id); row.script = doc; db2.commit(); db2.close()
    resp = client.post(f"/api/projects/{p.id}/ui-runs", json={"script_id": s.id}, headers=ah)
    assert resp.status_code == 201
    run_id = resp.json()["id"]
    for _ in range(50):  # 等 run 真正进入执行(约第 2 步时动手)
        if client.get(f"/api/ui-runs/{run_id}", headers=ah).json()["status"] == "running":
            break
        _t.sleep(0.2)
    _t.sleep(1.8)  # 落在第 2~3 步之间
    assert client.post(f"/api/ui-runs/{run_id}/force-finish", headers=ah).status_code == 200
    for _ in range(100):  # 线程在步骤边界自杀后执行槽必须全部归还(Task 12 后容量=settings.run_slot_count,上限 20s)
        if runner.RUN_SLOT._value == runner.RUN_SLOT._initial_value:  # BoundedSemaphore 内部字段:剩余许可/总容量
            break
        _t.sleep(0.2)
    else:
        pytest.fail("强制结束后执行线程未退出,RUN_SLOT 未释放")
    st = client.get(f"/api/ui-runs/{run_id}", headers=ah).json()
    assert st["status"] == "failed" and "强制结束" in st["error"]  # 迟到落库未翻案
