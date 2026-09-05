# tests/test_ui_isolation.py
"""Task 8:UI 自动化四路由(ui_scripts/ui_runs/ui_recordings/ui_auth_states)项目级隔离测试。
角色口径(简报):执行/录制 start/登录态 save 等写 = editor+;脚本与执行记录读 = viewer;
ui_runs / ui_recordings 的 SSE events 端点闸 editor;强制结束 = editor。
_auth helper 从 tests/test_project_isolation.py(Task 5 修正版)复制为同型 helper。
注:简报样例的 UiScriptSave 字段(script_name/mode/doc)与真实契约不符,
真实必填为 name + script(app/schemas.py),断言语义(viewer 执行→403 / outsider→404)不变。"""

from dataclasses import dataclass

DOC = {"version": 1, "meta": {"start_url": "https://x.com"}, "variables": [], "steps": []}


def _admin_headers(client, db_session):
    """bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    """建用户+分配项目+登录,返回 Authorization 头。(复制自 Task 5 修正版:归一化空元组缺省)"""
    u = make_user(db_session, name)
    from app.models import Project, ProjectMember

    if project_ids is None:
        pids: list[int] = []
    elif isinstance(project_ids, (list, tuple)):
        pids = list(project_ids)
    else:
        pids = [project_ids]
    for pid in pids:
        if db_session.get(Project, pid) is None:
            db_session.add(Project(name=f"p-{pid}"))
            db_session.flush()
        db_session.add(ProjectMember(project_id=pid, user_id=u.id, role=role))
    db_session.commit()
    r = client.post("/api/auth/login", json={"username": name, "password": f"pw-{name}"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _project(client, ah, name):
    return client.post("/api/projects", json={"name": name}, headers=ah).json()["id"]


def _script(client, ah, pid, name="s1"):
    return client.post(f"/api/projects/{pid}/ui-scripts",
                       json={"name": name, "script": DOC}, headers=ah).json()["id"]


def _seed_run(db_session, pid, sid, status="running"):
    """admin 直插 UiRun 行(绕过执行闸门/不开浏览器),返回 run id。"""
    from app.models import UiRun

    run = UiRun(project_id=pid, script_id=sid, script_name="s", mode="headless", status=status)
    db_session.add(run)
    db_session.commit()
    return run.id


# ── ui_scripts:创建/改/删 = editor,读 = viewer,无关系 = 404 ────────────────────


def test_viewer_cannot_run_script(client, db_session, make_user):
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    ah = {"Authorization": f"Bearer {atok}"}
    pid = client.post("/api/projects", json={"name": "u1"}, headers=ah).json()["id"]
    sid = client.post(f"/api/projects/{pid}/ui-scripts",
                      json={"name": "s1", "script": DOC}, headers=ah).json()["id"]
    vh = _auth(client, db_session, make_user, "vui", project_ids=[pid], role="viewer")
    r = client.post(f"/api/projects/{pid}/ui-runs", json={"script_id": sid}, headers=vh)
    assert r.status_code == 403  # viewer 不能执行


def test_outsider_script_is_404(client, db_session, make_user):
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    atok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    ah = {"Authorization": f"Bearer {atok}"}
    pid = _project(client, ah, "uout-p")
    sid = _script(client, ah, pid)
    oh = _auth(client, db_session, make_user, "uout")
    assert client.get("/api/ui-scripts/999999", headers=oh).status_code == 404
    # 别人项目的脚本同样不可见(对象级 404,非 403)
    assert client.get(f"/api/ui-scripts/{sid}", headers=oh).status_code == 404
    assert client.get(f"/api/projects/{pid}/ui-scripts", headers=oh).status_code == 404


def test_script_viewer_read_only(client, db_session, make_user):
    """viewer:列表/详情 200;创建/更新/删除 403(角色不足,而非 404)。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "vread-p")
    sid = _script(client, ah, pid)
    vh = _auth(client, db_session, make_user, "vscript", project_ids=[pid], role="viewer")
    assert client.get(f"/api/projects/{pid}/ui-scripts", headers=vh).status_code == 200
    assert client.get(f"/api/ui-scripts/{sid}", headers=vh).status_code == 200
    assert client.post(f"/api/projects/{pid}/ui-scripts", json={"name": "x", "script": DOC},
                       headers=vh).status_code == 403
    assert client.put(f"/api/ui-scripts/{sid}", json={"name": "x", "script": DOC},
                      headers=vh).status_code == 403
    assert client.delete(f"/api/ui-scripts/{sid}", headers=vh).status_code == 403


def test_script_editor_can_write(client, db_session, make_user):
    """editor 成员:创建/更新/删除全通(闸门只挡 viewer,不误伤 editor)。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "ed-p")
    sid = _script(client, ah, pid)
    eh = _auth(client, db_session, make_user, "edscript", project_ids=[pid], role="editor")
    r = client.post(f"/api/projects/{pid}/ui-scripts", json={"name": "e", "script": DOC}, headers=eh)
    assert r.status_code == 201
    assert client.put(f"/api/ui-scripts/{sid}", json={"name": "e2", "script": DOC},
                      headers=eh).status_code == 200
    assert client.delete(f"/api/ui-scripts/{sid}", headers=eh).status_code == 204


def test_script_outsider_write_is_404(client, db_session, make_user):
    """非成员对脚本创建/改/删:项目不存在语义 404(不暴露项目存在性)。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "out2-p")
    sid = _script(client, ah, pid)
    oh = _auth(client, db_session, make_user, "out2")
    assert client.post(f"/api/projects/{pid}/ui-scripts", json={"name": "x", "script": DOC},
                       headers=oh).status_code == 404
    assert client.put(f"/api/ui-scripts/{sid}", json={"name": "x", "script": DOC},
                      headers=oh).status_code == 404
    assert client.delete(f"/api/ui-scripts/{sid}", headers=oh).status_code == 404


# ── ui_runs:执行/强制结束/SSE = editor,读 = viewer,无关系 = 404 ───────────────


def test_run_viewer_read_editor_gate(client, db_session, make_user):
    """viewer:run 详情/列表 200;强制结束 403;outsider:详情 404。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "run-p")
    sid = _script(client, ah, pid)
    run_id = _seed_run(db_session, pid, sid)
    vh = _auth(client, db_session, make_user, "vrun", project_ids=[pid], role="viewer")
    oh = _auth(client, db_session, make_user, "orun")
    assert client.get(f"/api/ui-runs/{run_id}", headers=vh).status_code == 200
    assert client.get(f"/api/projects/{pid}/ui-runs", headers=vh).status_code == 200
    assert client.post(f"/api/ui-runs/{run_id}/force-finish", headers=vh).status_code == 403
    assert client.get(f"/api/ui-runs/{run_id}", headers=oh).status_code == 404
    assert client.post(f"/api/ui-runs/{run_id}/force-finish", headers=oh).status_code == 404


def test_run_editor_can_force_finish(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "runed-p")
    sid = _script(client, ah, pid)
    run_id = _seed_run(db_session, pid, sid)
    eh = _auth(client, db_session, make_user, "edrun", project_ids=[pid], role="editor")
    assert client.post(f"/api/ui-runs/{run_id}/force-finish", headers=eh).status_code == 200


def test_run_create_gates(client, db_session, make_user):
    """执行发起:viewer 403(角色不足);outsider 404;admin 正常 201 校验链保持
    (脚本不合法仍 400,登录态跨项目仍 400 —— 计划 8 校验不被闸门吃掉)。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "runc-p")
    pid2 = _project(client, ah, "runc-p2")
    sid = _script(client, ah, pid)
    bad_sid = _script(client, ah, pid, name="bad")
    # 另开会话改脚本(本用例 db_session 的事务快照早于 API 落库,REPEATABLE READ 下不可见)
    from app.database import SessionLocal
    from app.models import UiScript

    db2 = SessionLocal()
    try:
        row = db2.get(UiScript, bad_sid)
        row.script = {"version": 1, "meta": {}, "variables": [], "steps": [{"id": "x", "action": "fly"}]}
        db2.commit()
    finally:
        db2.close()
    from app.models import UiAuthState

    auth_row = UiAuthState(project_id=pid2, name="n", storage_path="auth/none.json")
    db_session.add(auth_row)
    db_session.commit()
    vh = _auth(client, db_session, make_user, "vrunc", project_ids=[pid], role="viewer")
    oh = _auth(client, db_session, make_user, "orunc")
    assert client.post(f"/api/projects/{pid}/ui-runs", json={"script_id": sid},
                       headers=vh).status_code == 403
    assert client.post(f"/api/projects/{pid}/ui-runs", json={"script_id": sid},
                       headers=oh).status_code == 404
    # admin 过闸后,原有业务校验不缺失
    assert client.post(f"/api/projects/{pid}/ui-runs", json={"script_id": bad_sid},
                       headers=ah).status_code == 400
    assert client.post(f"/api/projects/{pid}/ui-runs",
                       json={"script_id": sid, "auth_state_id": auth_row.id},
                       headers=ah).status_code == 400


def test_run_screenshot_gate(client, db_session, make_user, tmp_path, monkeypatch):
    """截图读:viewer 可达文件检查(无文件→404 not found);outsider 被闸在项目层
    (404 project not found)。两者都 404,但语义分层以 detail 区分锁死。
    ui_data_dir 指 tmp:仓库 ../data/ui 里留有历史执行截图,行 id 截断复位后会误命中。"""
    from app.config import settings

    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "shot-p")
    sid = _script(client, ah, pid)
    run_id = _seed_run(db_session, pid, sid)
    vh = _auth(client, db_session, make_user, "vshot", project_ids=[pid], role="viewer")
    oh = _auth(client, db_session, make_user, "oshot")
    r = client.get(f"/api/ui-runs/{run_id}/screens/step_0_passed.jpg", headers=vh)
    assert r.status_code == 404 and r.json()["detail"] == "not found"
    r2 = client.get(f"/api/ui-runs/{run_id}/screens/step_0_passed.jpg", headers=oh)
    assert r2.status_code == 404 and r2.json()["detail"] == "project not found"


def test_run_events_sse_editor_gate(client, db_session, make_user):
    """SSE 预览流:viewer 403;outsider 404(闸门在订阅前,不留半开流)。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "sse-p")
    sid = _script(client, ah, pid)
    run_id = _seed_run(db_session, pid, sid)
    vh = _auth(client, db_session, make_user, "vsse", project_ids=[pid], role="viewer")
    oh = _auth(client, db_session, make_user, "osse")
    assert client.get(f"/api/ui-runs/{run_id}/events", headers=vh).status_code == 403
    assert client.get(f"/api/ui-runs/{run_id}/events", headers=oh).status_code == 404


# ── ui_recordings:start/会话操作/SSE = editor(会话无库行,启动时记录 project_id)──


@dataclass
class _FakeRec:
    """假录制会话:只实现被路由触碰的方法,全程不起浏览器。"""
    project_id: int = 0
    stopped: bool = False
    _steps: list = None

    def __post_init__(self):
        self._steps = []

    def insert_assert(self, target, assert_type, text, mode):
        self._steps.append({"id": f"a{len(self._steps) + 1}", "action": assert_type})

    def stop(self):
        self.stopped = True
        return {"meta": {"start_url": ""}, "variables": [], "steps": list(self._steps)}

    def steps(self):
        return list(self._steps)


def _inject_recording(rid: int, pid: int):
    """绕过 start_recording 直接占一个 rid 并注入假会话(带 project_id 供闸门回溯)。"""
    from app.routers import ui_recordings as mod

    with mod._lock:
        mod._sessions[rid] = mod.RecSession(_FakeRec(), pid)
    return rid


def test_recording_start_gates(client, db_session, make_user):
    """录制 start:viewer 403 / outsider 404(闸门先于交互槽,不真开浏览器)。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "rec-p")
    vh = _auth(client, db_session, make_user, "vrec", project_ids=[pid], role="viewer")
    oh = _auth(client, db_session, make_user, "orec")
    assert client.post(f"/api/projects/{pid}/ui-recordings", json={},
                       headers=vh).status_code == 403
    assert client.post(f"/api/projects/{pid}/ui-recordings", json={},
                       headers=oh).status_code == 404


def test_recording_session_gates(client, db_session, make_user):
    """活跃录制会话对象级闸门:viewer 操作会话 403 且会话不被破坏;
    outsider 404(无关系即无此会话);editor 可 stop 产草稿。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "recs-p")
    other_pid = _project(client, ah, "recs-p2")
    vh = _auth(client, db_session, make_user, "vrecs", project_ids=[pid], role="viewer")
    eh = _auth(client, db_session, make_user, "edrecs", project_ids=[pid], role="editor")
    oh = _auth(client, db_session, make_user, "orecs", project_ids=[other_pid], role="editor")
    from app.routers import ui_recordings as mod

    rid = _inject_recording(next(mod._ids), pid)
    try:
        body = {"target": {"tag": "div"}, "assert_type": "assert_visible"}
        # viewer:插断言/停会话一律 403,且会话原样保留(不能借 404/写操作毁掉别人录制)
        assert client.post(f"/api/ui-recordings/{rid}/assert", json=body, headers=vh).status_code == 403
        assert client.post(f"/api/ui-recordings/{rid}/stop", headers=vh).status_code == 403
        assert client.post(f"/api/ui-recordings/{rid}/cancel", headers=vh).status_code == 403
        assert client.get(f"/api/ui-recordings/{rid}/events", headers=vh).status_code == 403
        assert rid in mod._sessions
        # 别的项目成员:404(与「会话不存在」同语义,不暴露会话存在性)
        assert client.post(f"/api/ui-recordings/{rid}/stop", headers=oh).status_code == 404
        # editor:可插断言、可停止拿草稿
        r = client.post(f"/api/ui-recordings/{rid}/assert", json=body, headers=eh)
        assert r.status_code == 200 and r.json()["steps"][0]["action"] == "assert_visible"
        r2 = client.post(f"/api/ui-recordings/{rid}/stop", headers=eh)
        assert r2.status_code == 200 and "steps" in r2.json()
    finally:
        with mod._lock:
            mod._sessions.pop(rid, None)


# ── ui_auth_states:collect/save/cancel/删除 = editor,读 = viewer ───────────────


@dataclass
class _FakeCollectSession:
    cid: int
    stopped: bool = False

    def browser_context(self):
        return self

    def storage_state(self, path):
        from pathlib import Path

        Path(path).write_text('{"cookies": [], "origins": []}', encoding="utf-8")
        return {"cookies": [], "origins": []}

    def call(self, fn):
        return fn()

    def stop(self):
        from app.routers import ui_auth_states as mod

        self.stopped = True
        with mod._lock:
            mod._collects.pop(self.cid, None)


def _inject_collect(pid: int):
    from app.routers import ui_auth_states as mod

    cid = next(mod._ids)
    fake = _FakeCollectSession(cid)
    with mod._lock:
        mod._collects[cid] = mod.CollectSession(fake, pid, "n")
    return cid, fake


def test_auth_state_viewer_read_only(client, db_session, make_user):
    """viewer:列表 200;删除登录态 403。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "authv-p")
    vh = _auth(client, db_session, make_user, "vauth", project_ids=[pid], role="viewer")
    assert client.get(f"/api/projects/{pid}/ui-auth-states", headers=vh).status_code == 200
    from app.models import UiAuthState

    row = UiAuthState(project_id=pid, name="n", storage_path="auth/none.json")
    db_session.add(row)
    db_session.commit()
    assert client.delete(f"/api/ui-auth-states/{row.id}", headers=vh).status_code == 403


def test_auth_state_outsider_404(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "autho-p")
    from app.models import UiAuthState

    row = UiAuthState(project_id=pid, name="n", storage_path="auth/none.json")
    db_session.add(row)
    db_session.commit()
    oh = _auth(client, db_session, make_user, "oauth")
    assert client.get(f"/api/projects/{pid}/ui-auth-states", headers=oh).status_code == 404
    assert client.delete(f"/api/ui-auth-states/{row.id}", headers=oh).status_code == 404
    assert client.post(f"/api/projects/{pid}/ui-auth-states/collect", json={"name": "n"},
                       headers=oh).status_code == 404


def test_auth_state_save_editor_gate(client, db_session, make_user, tmp_path, monkeypatch):
    """save 闸门:viewer 403 且采集会话不被消费(所有权未移交,admin 仍可 save 成功);
    editor save 正常落库;cancel 同为 editor。"""
    from app.config import settings
    from app.routers import ui_auth_states as mod

    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "auths-p")
    vh = _auth(client, db_session, make_user, "vauths", project_ids=[pid], role="viewer")
    eh = _auth(client, db_session, make_user, "edauths", project_ids=[pid], role="editor")
    cid, _fake = _inject_collect(pid)
    try:
        # viewer save → 403,且会话仍在册(不能借 save 毁掉别人的采集会话)
        assert client.post(f"/api/ui-auth-collect/{cid}/save", headers=vh).status_code == 403
        assert cid in mod._collects
        # editor save → 201
        r = client.post(f"/api/ui-auth-collect/{cid}/save", headers=eh)
        assert r.status_code == 201 and r.json()["project_id"] == pid
        assert cid not in mod._collects
    finally:
        with mod._lock:
            mod._collects.pop(cid, None)
    # cancel 同口径:viewer 403 且会话保留,editor 取消成功
    cid2, fake2 = _inject_collect(pid)
    try:
        assert client.post(f"/api/ui-auth-collect/{cid2}/cancel", headers=vh).status_code == 403
        assert cid2 in mod._collects
        assert client.post(f"/api/ui-auth-collect/{cid2}/cancel", headers=eh).status_code == 204
        assert fake2.stopped is True
    finally:
        with mod._lock:
            mod._collects.pop(cid2, None)


def test_auth_state_collect_editor_gate(client, db_session, make_user):
    """采集 start:viewer 403(先于交互槽,不真开浏览器);editor 201(假会话注入不动真浏览器)。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "authc-p")
    vh = _auth(client, db_session, make_user, "vauthc", project_ids=[pid], role="viewer")
    assert client.post(f"/api/projects/{pid}/ui-auth-states/collect", json={"name": "n"},
                       headers=vh).status_code == 403
