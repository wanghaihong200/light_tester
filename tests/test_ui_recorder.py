# tests/test_ui_recorder.py
"""录制会话测试:headless 模式程序化点击驱动真实 chromium,验证事件采集/DSL 映射/断言候选;
HTTP 冒烟只打 404/409 分支,不真开会话。"""
import itertools
import threading
import time
from pathlib import Path

import pytest

from app.jobs.bus import JobEventBus
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


def _admin_headers(client):
    """Task 8 补鉴权:业务端点全量 401 后,HTTP 冒烟走 admin 头(保语义,补鉴权)。"""
    from app.bootstrap import ensure_bootstrap_admin
    from app.database import SessionLocal as SL

    db = SL()
    try:
        ensure_bootstrap_admin(db)
    finally:
        db.close()
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_recording_api_404(client):
    ah = _admin_headers(client)
    # 先确认路由确实注册了:否则下面的 404 分不清是「无会话」还是「无路由」
    spec = client.get("/openapi.json").json()["paths"]
    for p in ("/api/projects/{project_id}/ui-recordings", "/api/ui-recordings/{rid}/events",
              "/api/ui-recordings/{rid}/assert", "/api/ui-recordings/{rid}/stop",
              "/api/ui-recordings/{rid}/cancel"):
        assert p in spec, p
    assert client.get("/api/ui-recordings/9999/events", headers=ah).status_code == 404
    r = client.post("/api/ui-recordings/9999/assert",
                    json={"target": {"tag": "div"}, "assert_type": "assert_visible"}, headers=ah)
    assert r.status_code == 404
    assert client.post("/api/ui-recordings/9999/stop", headers=ah).status_code == 404
    assert client.post("/api/ui-recordings/9999/cancel", headers=ah).status_code == 404
    assert client.post("/api/projects/9999/ui-recordings", json={}, headers=ah).status_code == 404


def test_recording_api_409_when_slot_occupied(client):
    """全局并发=1:INTERACTIVE_SLOT 被占时创建录制必须 409,且不产出 recording_id。"""
    ah = _admin_headers(client)
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
        r = client.post(f"/api/projects/{pid}/ui-recordings", json={}, headers=ah)
        assert r.status_code == 409
        assert "会话" in r.json()["detail"]
    finally:
        INTERACTIVE_SLOT.release()


# ── 纯映射单测:不起浏览器,跳过 __init__(其会自动开会话)手工填最小字段,
#    直接驱动 _on_raw/insert_assert/stop,锁死增量同步的确定性契约 ──
def _bare_session(on_event) -> RecordingSession:
    s = RecordingSession.__new__(RecordingSession)
    s.recording_id = 1
    s.on_event = on_event
    s._bus = JobEventBus()  # 无订阅者,投递即空操作(单测不起主循环)
    s._close_cb = lambda: None
    s._headless = True
    s._storage_path = None
    s._start_url = ""
    s._raw, s._main, s._asserts = [], [], []
    s._ids = itertools.count(1)
    s._lock = threading.Lock()
    s._session = None
    s._started = True
    return s


_INPUT = {"tag": "input", "id": "user", "placeholder": "用户名"}


def _streamed_steps(events: list[dict]) -> list[dict]:
    return [e["step"] for e in events if e["type"] == "action"]


def test_incremental_sync_keeps_step_id_stable():
    """逐字输入 5 次:每次都推流,但 fill 的 id 恒定(原位刷新)、文本恒为最新值;终稿沿用同一 id。"""
    events: list[dict] = []
    s = _bare_session(events.append)
    for v in ("a", "ad", "adm", "admi", "admin"):
        s._on_raw({"kind": "input", "target": _INPUT, "value": v})
    fills = [x for x in _streamed_steps(events) if x["action"] == "fill"]
    assert len(fills) == 5
    assert {f["id"] for f in fills} == {fills[0]["id"]}
    assert [f["params"]["text"] for f in fills] == ["a", "ad", "adm", "admi", "admin"]
    draft = s.stop()
    fill = next(x for x in draft["steps"] if x["action"] == "fill")
    assert (fill["id"], fill["params"]["text"]) == (fills[0]["id"], "admin")


def test_assert_interleaves_at_before_len_and_matches_stream():
    """断言落在插入时的主干位置(同位保持插入顺序);流式步骤与 stop 终稿逐条一致。"""
    events: list[dict] = []
    s = _bare_session(events.append)
    btn = {"tag": "button", "text": "登录"}
    s._on_raw({"kind": "click", "target": btn})        # 主干[0]:click
    s._on_raw({"kind": "goto", "url": "http://x/a"})   # 主干[1]:goto(before_len=2)
    a1 = s.insert_assert(btn, "assert_visible", None, None)
    a2 = s.insert_assert(btn, "assert_text", "登录", "contains")
    s._on_raw({"kind": "goto", "url": "http://x/b"})   # 主干[2]:须排在断言之后
    draft = s.stop()
    actions = [x["action"] for x in draft["steps"]]
    assert actions == ["click", "goto", "assert_visible", "assert_text", "goto"]
    ids = [x["id"] for x in draft["steps"]]
    assert ids.index(a1["id"]) == 2 and ids.index(a2["id"]) == 3
    assert draft["steps"] == _streamed_steps(events)


# ── 预览帧采集(capture_frames,窗口抖动修复 2026-09-03)──────────────────


def test_interactive_frames_on_by_default(page_url):
    """默认推帧(录制面板依赖);帧改 CDP 直采后仍正常到达。"""
    from app.ui_automation.session import InteractiveSession
    frames: list[str] = []
    sess = InteractiveSession(session_id=9910, headless=True, start_url=page_url,
                              storage_state=None, on_raw=lambda e: None,
                              on_frame=frames.append, on_close=lambda: None)
    try:
        sess.current_page(timeout=15)
        time.sleep(2.0)  # ≥3 个帧周期(0.6s/帧)
    finally:
        sess.stop()
        sess.join(timeout=10)
    assert len(frames) >= 2


def test_capture_frames_false_no_frames(page_url):
    """无预览面板的会话(登录态采集)capture_frames=False:完全不采帧,窗口零扰动。"""
    from app.ui_automation.session import InteractiveSession
    frames: list[str] = []
    sess = InteractiveSession(session_id=9911, headless=True, start_url=page_url,
                              storage_state=None, on_raw=lambda e: None,
                              on_frame=frames.append, on_close=lambda: None,
                              capture_frames=False)
    try:
        sess.current_page(timeout=15)
        time.sleep(2.0)  # 若仍在采帧,这里会有 ~3 帧
    finally:
        sess.stop()
        sess.join(timeout=10)
    assert frames == []


# ── 点击红圈特效(CLICK_FX_JS,2026-09-03 冒烟需求 3)──────────────────


def test_click_fx_ripple_on_recorded_click(page_url):
    """录制会话点击出红圈(data-tc-fx);断言模式点击不出(断言不是录制步骤)。"""
    sess = RecordingSession(recording_id=9903, headless=True, start_url=page_url,
                            storage_state=None, on_close=lambda: None)
    try:
        page = sess.current_page(timeout=15)
        # 工具条真实导航渲染回归:document-start 抛 appendChild null 曾致其从未出现
        assert page.evaluate("!!document.querySelector('div[style*=fixed]')")
        page.click("#user")  # #user 有尺寸且无导航行为,红圈可存活供断言(#out 零尺寸点不了)
        time.sleep(0.3)
        assert page.evaluate("!!document.querySelector('[data-tc-fx]')")

        page.evaluate("document.querySelectorAll('[data-tc-fx]').forEach(e => e.remove())")
        page.evaluate("window.__tcAssertMode = true")
        page.click("#user")
        time.sleep(0.3)
        assert page.evaluate("document.querySelectorAll('[data-tc-fx]').length") == 0
        sess.stop()
    finally:
        sess.join(timeout=10)


def test_click_fx_absent_without_toolbar(page_url):
    """with_toolbar=False(登录态采集会话)不注入特效:__tcClickFx 未定义、点击无红圈。"""
    from app.ui_automation.session import InteractiveSession
    sess = InteractiveSession(session_id=9912, headless=True, start_url=page_url,
                              storage_state=None, on_raw=lambda e: None,
                              on_frame=lambda b64: None, on_close=lambda: None,
                              with_toolbar=False, capture_frames=False)
    try:
        page = sess.current_page(timeout=15)
        page.click("#user")
        time.sleep(0.3)
        assert page.evaluate("window.__tcClickFx === undefined")
        assert page.evaluate("document.querySelectorAll('[data-tc-fx]').length") == 0
        sess.stop()
    finally:
        sess.join(timeout=10)


def test_recording_captures_scroll(tmp_path):
    """滚轮/拖滚动条录制(需求2):真实 mouse.wheel → scroll 事件 400ms 防抖 → 草稿含 scroll 步骤。"""
    f = tmp_path / "long.html"
    f.write_text('<html><body style="margin:0"><div style="height:3000px">tall</div></body></html>',
                 encoding="utf-8")
    draft_box = {}
    sess = RecordingSession(recording_id=9904, headless=True, start_url=f.as_uri(),
                            storage_state=None, on_close=lambda: None)
    try:
        page = sess.current_page(timeout=15)
        page.mouse.wheel(0, 600)
        time.sleep(0.7)  # ≥ 防抖窗口 400ms,让滚动批量结算
        draft_box.update(sess.stop())
    finally:
        sess.stop()
        sess.join(timeout=10)
    scrolls = [s for s in draft_box["steps"] if s["action"] == "scroll"]
    assert len(scrolls) == 1 and scrolls[0]["params"]["dy"] >= 500 and scrolls[0]["params"]["dx"] == 0
