"""Task 9(计划 12):app_runs 路由 API 测试——执行发起(单/分发批量同端点)+ SSE + 强制结束。

对 brief 样例的仓内现状对齐(非行为偏离,断言点不变):
- _admin_headers 实际签名是 (client, db_session)(Task 7 落地形态),各用例补 db_session 入参;
- 登录响应字段是 token 不是 access_token(app/routers/auth.py:LoginOut(token=…),计划稿笔误);
- 补 autouse TRUNCATE app_runs/app_scripts 清理(conftest._TABLES 未含,同 tests/test_app_models.py):
  projects 被复位自增后每用例复用同一 project_id,不清理则列表计数断言被前序用例残留行污染。"""

import pytest
from sqlalchemy import text

from app.app_automation import devices as app_devices
from app.app_automation import executor
from app.database import SessionLocal
from app.routers import app_runs as router_mod

from tests.test_app_scripts_api import _CASE, _admin_headers, _mk_project


@pytest.fixture(autouse=True)
def _clean_app_tables():
    """本文件会写 app_runs/app_scripts 行;conftest._TABLES 未含这两表,projects 被 TRUNCATE
    复位自增后每用例复用同一 project_id,残留行会串项目污染列表计数断言与全量回归。"""
    yield
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        session.execute(text("TRUNCATE TABLE app_runs"))
        session.execute(text("TRUNCATE TABLE app_scripts"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        session.commit()
    finally:
        session.close()


class _StubThread:
    """不真正起线程(执行器另有单测);只记录,锁不释放——需释放的用例手动触发 target。"""

    last = None

    def __init__(self, target=None, args=(), daemon=False):
        self.target, self.args = target, args
        _StubThread.last = self

    def start(self):
        pass


@pytest.fixture
def stub_thread(monkeypatch):
    monkeypatch.setattr(router_mod.threading, "Thread", _StubThread)
    yield


@pytest.fixture(autouse=True)
def _clean_locks():
    app_devices.DEVICE_LOCKS.clear()
    executor._FORCE_FINISHED.clear()
    yield
    app_devices.DEVICE_LOCKS.clear()
    executor._FORCE_FINISHED.clear()


@pytest.fixture(autouse=True)
def _restore_run_slots():
    """_StubThread 不执行 _run_thread 的 finally,RUN_SLOT 占了不还;本文件每个发起执行的
    用例都真实占槽,累计会榨干全局 5 槽,让同进程随后跑的 ui_runs 用例全部 409。
    这里按容量补齐归还(私有 _value 访问先例:tests/test_run_slot.py 的 _initial_value)。"""
    from app.config import settings
    from app.ui_automation import runner

    yield
    while runner.RUN_SLOT._value < settings.run_slot_count:
        runner.RUN_SLOT.release()


def _mk_script(client, h, pid) -> int:
    r = client.post(f"/api/projects/{pid}/app-scripts", headers=h, json={"case": _CASE})
    assert r.status_code == 201
    return r.json()["id"]


def test_create_single_run_201(client, db_session, stub_thread):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "单执行项目")
    sid = _mk_script(client, h, pid)
    r = client.post(f"/api/projects/{pid}/app-runs", headers=h,
                    json={"script_id": sid, "device_serials": ["DEV-A"]})
    assert r.status_code == 201, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["device_serial"] == "DEV-A"
    assert rows[0]["batch_id"] is None


def test_create_fanout_shares_batch_id(client, db_session, stub_thread):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "批量项目")
    sid = _mk_script(client, h, pid)
    r = client.post(f"/api/projects/{pid}/app-runs", headers=h,
                    json={"script_id": sid, "device_serials": ["DEV-A", "DEV-B"],
                          "perf_items": ["CPU"], "startup_time": True})
    assert r.status_code == 201
    rows = r.json()
    assert len(rows) == 2
    assert rows[0]["batch_id"] and rows[0]["batch_id"] == rows[1]["batch_id"]
    assert {row["device_serial"] for row in rows} == {"DEV-A", "DEV-B"}
    assert rows[0]["perf_items"] == ["CPU"]


def test_device_busy_409_and_all_or_nothing(client, db_session, stub_thread):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "占用项目")
    sid = _mk_script(client, h, pid)
    # 预占 DEV-B 锁(模拟忙)
    app_devices.lock_for("DEV-B").acquire()
    r = client.post(f"/api/projects/{pid}/app-runs", headers=h,
                    json={"script_id": sid, "device_serials": ["DEV-A", "DEV-B"]})
    assert r.status_code == 409
    assert "DEV-B" in r.json()["detail"]
    # all-or-nothing:DEV-A 的锁必须已回滚(可立即再次获取)
    assert app_devices.lock_for("DEV-A").acquire(blocking=False) is True


def test_high_risk_and_checks_gates(client, db_session, stub_thread):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "闸门项目")
    sid = _mk_script(client, h, pid)
    # 检查点形状非法 → 400
    r = client.post(f"/api/projects/{pid}/app-runs", headers=h,
                    json={"script_id": sid, "device_serials": ["DEV-A"],
                          "pre_checks": [{"type": "hack"}]})
    assert r.status_code == 400
    # 空设备列表 → 422(pydantic min_length)
    r2 = client.post(f"/api/projects/{pid}/app-runs", headers=h,
                     json={"script_id": sid, "device_serials": []})
    assert r2.status_code == 422
    # 重复设备 → 400
    r3 = client.post(f"/api/projects/{pid}/app-runs", headers=h,
                     json={"script_id": sid, "device_serials": ["DEV-A", "DEV-A"]})
    assert r3.status_code == 400


def test_list_and_detail_and_sse_terminal(client, db_session, stub_thread):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "查询项目")
    sid = _mk_script(client, h, pid)
    rows = client.post(f"/api/projects/{pid}/app-runs", headers=h,
                       json={"script_id": sid, "device_serials": ["DEV-A"]}).json()
    rid = rows[0]["id"]
    assert len(client.get(f"/api/projects/{pid}/app-runs", headers=h).json()) == 1
    assert client.get(f"/api/app-runs/{rid}", headers=h).json()["id"] == rid
    # 手动置终态后订阅:SSE 立即回 status+snapshot 并断流
    from app.models import AppRun
    with SessionLocal() as db:
        run = db.get(AppRun, rid)
        run.status = "passed"
        run.run_state = "passed"
        db.commit()
    resp = client.get(f"/api/app-runs/{rid}/events" + f"?token={_sse_token(client)}", headers=None)
    assert resp.status_code == 200
    assert "snapshot" in resp.text and "passed" in resp.text


def _sse_token(client):
    from tests.test_app_scripts_api import _admin_headers  # 复用登录拿 token
    return client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]


def test_force_finish(client, db_session, stub_thread):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "强停项目")
    sid = _mk_script(client, h, pid)
    rid = client.post(f"/api/projects/{pid}/app-runs", headers=h,
                      json={"script_id": sid, "device_serials": ["DEV-A"]}).json()[0]["id"]
    r = client.post(f"/api/app-runs/{rid}/force-finish", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    assert r.json()["error"] == "用户强制结束"
    # 已终态再强停 → 400
    assert client.post(f"/api/app-runs/{rid}/force-finish", headers=h).status_code == 400
    assert rid in executor._FORCE_FINISHED  # 协作取消标志已置
