# tests/test_ui_auth_states.py
"""登录态管理测试:HTTP 只打 404/400/409/软删等便宜分支(不真开浏览器会话);
storage_state 加载走 runner 集成链路(headless 真开 chromium,补 Task 4 未实测的分支)。"""
import itertools
import time
from pathlib import Path

import pytest

from app.config import settings
from app.jobs.bus import JobEventBus
from app.models import Project, UiAuthState, UiRun, UiScript
from app.routers import ui_auth_states as mod
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


# ── save 命名回归:假会话注入 _collects,不起浏览器(修复 round 1) ──
class _FakeCtx:
    """假 context:storage_state 只按入参路径写 JSON,模拟真实导出落盘;
    exc 非空时改为抛该异常(模拟会话已坏 / 写盘失败两类导出故障)。"""

    def __init__(self, exc: BaseException | None = None):
        self.exc = exc

    def storage_state(self, path):
        if self.exc is not None:
            raise self.exc
        Path(path).write_text('{"cookies": [], "origins": []}', encoding="utf-8")
        return {"cookies": [], "origins": []}


class _FakeSession:
    """假采集会话:call 原地执行(等价会话线程),stop 记标记并自清出册(模拟真实
    on_close 回调),全程不碰 playwright。"""

    def __init__(self, cid: int, exc: BaseException | None = None):
        self._cid = cid
        self.exc = exc
        self.stopped = False

    def browser_context(self):
        return _FakeCtx(self.exc)

    def call(self, fn):
        return fn()

    def stop(self):
        self.stopped = True
        with mod._lock:  # 真会话 stop 后由会话线程 on_close 出册,这里原地等价
            mod._collects.pop(self._cid, None)


def _inject_collect(project_id: int, exc: BaseException | None = None):
    """绕过 start_collect(不真开浏览器)直接占一个 collect_id 并注入假会话。
    返回 (cid, 假会话本体),便于断言 stop 标记与切换故障注入。"""
    cid = next(mod._ids)
    fake = _FakeSession(cid, exc)
    with mod._lock:
        mod._collects[cid] = mod.CollectSession(fake, project_id, "n")
    return cid, fake


def _auth_rows(project_id: int) -> list[int]:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        return [r.id for r in db.query(UiAuthState)
                .filter(UiAuthState.project_id == project_id).all()]
    finally:
        db.close()


def test_save_twice_no_filename_collision(client, tmp_path, monkeypatch):
    """两次 save 的文件名以 DB 自增 id 命名:后端重启后进程内计数复用也不会覆盖旧登录态文件。"""
    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)  # 导出落 tmp,不脏仓库 data 目录
    pid = _mk_project()
    ids = []
    for _ in range(2):  # 同一进程内连续两次采集 save(不同行 id)
        cid, _cs = _inject_collect(pid)
        r = client.post(f"/api/ui-auth-collect/{cid}/save")
        assert r.status_code == 201
        ids.append(r.json()["id"])
    assert ids[0] != ids[1]  # 文件名跟着行 id 走,必不冲突
    assert mod._collects == {}  # save 即关会话
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        paths = {r.id: r.storage_path
                 for r in db.query(UiAuthState).filter(UiAuthState.project_id == pid).all()}
    finally:
        db.close()
    assert set(paths) == set(ids)
    for aid in ids:  # 各自独立落盘,且命名与行 id 一一对应
        assert paths[aid].endswith(f"{pid}_{aid}.json"), paths[aid]
        assert Path(paths[aid]).exists()
    assert paths[ids[0]] != paths[ids[1]]


# ── save 异常分流 + 所有权移交(Task 11:A1 Important2 / A2 Minor3)──
def test_save_runtime_error_409_cleans_session(client, tmp_path, monkeypatch):
    """导出抛 RuntimeError(会话/浏览器已关,重试必然再败)→ 409 且停止清理会话。"""
    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)
    pid = _mk_project()
    cid, fake = _inject_collect(pid, RuntimeError("session closed"))
    r = client.post(f"/api/ui-auth-collect/{cid}/save")
    assert r.status_code == 409
    assert "已结束" in r.json()["detail"]
    assert fake.stopped is True            # 会话已停止清理,用户须重新采集
    assert mod._collects == {}             # 不留在册:save/cancel 再来都是 404
    assert _auth_rows(pid) == []           # 占位行已回滚,不留孤儿


def test_save_io_error_500_keeps_session_for_retry(client, tmp_path, monkeypatch):
    """导出抛非 RuntimeError(写盘失败等,会话仍健康)→ 500 且保留会话,重试可成功。"""
    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)
    pid = _mk_project()
    cid, fake = _inject_collect(pid, OSError("disk full"))
    r = client.post(f"/api/ui-auth-collect/{cid}/save")
    assert r.status_code == 500
    assert "重试" in r.json()["detail"]
    assert fake.stopped is False           # 会话未被打断
    assert list(mod._collects) == [cid]    # 仍在册:save / cancel 都还能找到它
    assert _auth_rows(pid) == []           # 占位行已回滚,不留孤儿
    fake.exc = None                        # 故障解除,同一会话直接重试 save
    r2 = client.post(f"/api/ui-auth-collect/{cid}/save")
    assert r2.status_code == 201
    assert _auth_rows(pid) == [r2.json()["id"]]  # 恰好一行:失败那次的占位行已回滚
    assert mod._collects == {}


def test_save_dir_failure_500_keeps_session_for_retry(client, tmp_path, monkeypatch):
    """mkdir/落库段失败与导出失败同口径(Task 11 review M1):500 且会话回插可重试;
    若这些步骤游离在保护外,条目已被 pop → 裸 500 后重试 404、浏览器窗口占槽到用户手关窗。"""
    pid = _mk_project()
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")  # ui_data_dir 指向文件 → mkdir(parents=True) 必炸
    monkeypatch.setattr(settings, "ui_data_dir", blocker)
    cid, fake = _inject_collect(pid)
    r = client.post(f"/api/ui-auth-collect/{cid}/save")
    assert r.status_code == 500
    assert "重试" in r.json()["detail"]
    assert fake.stopped is False            # 会话未被打断,交互槽仍被本会话正常持有
    assert list(mod._collects) == [cid]     # 所有权回插:save/cancel 都还能找到它
    assert _auth_rows(pid) == []
    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)  # 故障解除,同一会话重试 save
    r2 = client.post(f"/api/ui-auth-collect/{cid}/save")
    assert r2.status_code == 201
    assert _auth_rows(pid) == [r2.json()["id"]]
    assert mod._collects == {}


def test_save_duplicate_second_404_single_row(client, tmp_path, monkeypatch):
    """重复 save:所有权移交,第二次 save 404,库里只落一行。"""
    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)
    pid = _mk_project()
    cid, _fake = _inject_collect(pid)
    assert client.post(f"/api/ui-auth-collect/{cid}/save").status_code == 201
    assert client.post(f"/api/ui-auth-collect/{cid}/save").status_code == 404
    assert len(_auth_rows(pid)) == 1
    assert mod._collects == {}


def test_save_concurrent_only_one_wins(tmp_path, monkeypatch):
    """并发 save 同一 cid:pop 所有权移交保证恰有一路落库,另一路 404(直接驱动路由函数,
    绕开 TestClient 单 portal,两线程真实竞速)。"""
    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)
    pid = _mk_project()
    cid, _fake = _inject_collect(pid)
    from threading import Thread

    from fastapi import HTTPException

    from app.database import SessionLocal

    outcomes: list[str] = []

    def attempt():
        db = SessionLocal()
        try:
            row = mod.save_collect(cid, db)
            outcomes.append(f"201:{row.id}")
        except HTTPException as e:
            outcomes.append(str(e.status_code))
        finally:
            db.close()

    ts = [Thread(target=attempt) for _ in range(2)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(10)
    assert sorted(o.split(":")[0] for o in outcomes) == ["201", "404"]
    assert len(_auth_rows(pid)) == 1
    assert mod._collects == {}


def test_recording_rejects_invalid_auth_state_id(client):
    """ui_recordings 的 auth_state_id 校验与 ui_runs 同源:不存在/跨项目/软删 一律 400,
    且先于占 INTERACTIVE_SLOT(槽被占满时仍是 400,证明不会带病去开浏览器会话)。"""
    pid_a, pid_b = _mk_project(), _mk_project()
    aid = _mk_auth(pid_a, "auth/none.json")
    import time

    from app.ui_automation.recorder import INTERACTIVE_SLOT as SLOT
    for _ in range(100):  # 预占交互槽:若校验缺失,路由会继续走 409/开会话而非 400
        if SLOT.acquire(blocking=False):
            break
        time.sleep(0.1)
    else:
        pytest.fail("INTERACTIVE_SLOT 被先前会话占住,无法预占")
    try:
        assert client.post(f"/api/projects/{pid_b}/ui-recordings",
                           json={"auth_state_id": 99999}).status_code == 400
        # 跨项目引用:登录态属于 pid_a,在 pid_b 下发起录制必须 400(Task 5 defer,Task 6 已修)
        assert client.post(f"/api/projects/{pid_b}/ui-recordings",
                           json={"auth_state_id": aid}).status_code == 400
        # 软删后不可再引用
        assert client.delete(f"/api/ui-auth-states/{aid}").status_code == 204
        assert client.post(f"/api/projects/{pid_b}/ui-recordings",
                           json={"auth_state_id": aid}).status_code == 400
    finally:
        SLOT.release()
