# tests/test_ui_recorder.py
"""录制会话测试:headless 模式程序化点击驱动真实 chromium,验证事件采集/DSL 映射/断言候选;
HTTP 冒烟只打 404/409 分支,不真开会话。"""
import time
from pathlib import Path

import pytest

from app.models import Project
from app.ui_automation.recorder import INTERACTIVE_SLOT, RecordingSession

PAGE = """<html><body>
<input id="user" placeholder="用户名"><button id="go">登录</button><div id="out"></div>
<script>document.getElementById('go').onclick=()=>{location.href='?ok=1'}</script>
</body></html>"""


@pytest.fixture()
def page_url(tmp_path: Path) -> str:
    f = tmp_path / "rec.html"; f.write_text(PAGE, encoding="utf-8"); return f.as_uri()


def test_recording_captures_actions(page_url):
    draft_box = {}
    sess = RecordingSession(recording_id=9901, headless=True, start_url=page_url,
                            storage_state=None, on_close=lambda: None)
    try:
        page = sess.current_page(timeout=15)
        page.fill("#user", "admin")           # 触发 input
        page.click("#go")                     # 触发 click + goto(跳转)
        time.sleep(1.0)                       # 等事件回流
        draft = sess.stop()
        draft_box.update(draft)
    finally:
        sess.join(timeout=10)
    steps = draft_box["steps"]
    actions = [s["action"] for s in steps]
    assert "goto" in actions and "fill" in actions and "click" in actions
    fill = next(s for s in steps if s["action"] == "fill")
    assert fill["params"]["text"] == "admin"
    assert fill["locator"]["strategy"] in ("placeholder", "css", "test_id", "label")


def test_assert_candidate_reported(page_url):
    events = []
    sess = RecordingSession(recording_id=9902, headless=True, start_url=page_url,
                            storage_state=None, on_close=lambda: None,
                            on_event=events.append)
    try:
        page = sess.current_page(timeout=15)
        page.evaluate("window.__tcAssertMode = true")  # 前端工具条切断言模式的等价物
        page.click("#go", force=True)
        time.sleep(1.0)
        assert any(e["type"] == "assert_candidate" for e in events)
        sess.stop()
    finally:
        sess.join(timeout=10)


def test_recording_api_404(client):
    # 先确认路由确实注册了:否则下面的 404 分不清是「无会话」还是「无路由」
    spec = client.get("/openapi.json").json()["paths"]
    for p in ("/api/projects/{project_id}/ui-recordings", "/api/ui-recordings/{rid}/events",
              "/api/ui-recordings/{rid}/assert", "/api/ui-recordings/{rid}/stop",
              "/api/ui-recordings/{rid}/cancel"):
        assert p in spec, p
    assert client.get("/api/ui-recordings/9999/events").status_code == 404
    r = client.post("/api/ui-recordings/9999/assert",
                    json={"target": {"tag": "div"}, "assert_type": "assert_visible"})
    assert r.status_code == 404
    assert client.post("/api/ui-recordings/9999/stop").status_code == 404
    assert client.post("/api/ui-recordings/9999/cancel").status_code == 404
    assert client.post("/api/projects/9999/ui-recordings", json={}).status_code == 404


def test_recording_api_409_when_slot_occupied(client):
    """全局并发=1:INTERACTIVE_SLOT 被占时创建录制必须 409,且不产出 recording_id。"""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        p = Project(name="ui-rec-p"); db.add(p); db.commit()
        pid = p.id
    finally:
        db.close()
    for _ in range(100):  # 等先前用例的交互会话释放锁(0.1s 间隔,上限 10s)
        if INTERACTIVE_SLOT.acquire(blocking=False):
            break
        time.sleep(0.1)
    else:
        pytest.fail("INTERACTIVE_SLOT 被先前会话占住,无法预占")
    try:
        r = client.post(f"/api/projects/{pid}/ui-recordings", json={})
        assert r.status_code == 409
        assert "会话" in r.json()["detail"]
    finally:
        INTERACTIVE_SLOT.release()
