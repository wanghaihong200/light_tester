"""supervisor:端口范围/分配/冲突预检/启停状态机(fake 探测)/探活状态迁移。"""
from types import SimpleNamespace as NS

import pytest

from app.mock_service import supervisor


@pytest.fixture(autouse=True)
def _clear_proc_registry():
    # _procs 是模块级注册表:fake 用例留在里面的 FakeProc(poll()==None 像"活着")会污染
    # 同 pytest 进程的后续用例(真子进程集成例被"句柄活"路径短路而不 spawn)→ 每用例后清空。
    yield
    supervisor._procs.clear()


def test_parse_port_range():
    assert supervisor.parse_port_range("9001-9499") == (9001, 9499)
    with pytest.raises(ValueError):
        supervisor.parse_port_range("abc")
    with pytest.raises(ValueError):
        supervisor.parse_port_range("9999-100")


def test_bind_and_port_in_use():
    import socket
    s = socket.socket()
    # brief 原稿绑 127.0.0.1 并断言"0.0.0.0 撞已监听端口(Windows/Linux 均然)"——Windows 实测
    # wildcard 可越过 specific(127.0.0.1)绑定成功(无 SO_EXCLUSIVEADDRUSE 时),前提不成立;
    # 改绑 0.0.0.0 与 bind_ok 同址冲突(同 wildcard→WSAEADDRINUSE),意图不变(占用的口要探出)。
    s.bind(("0.0.0.0", 0))
    s.listen(1)
    busy = s.getsockname()[1]
    try:
        # 0.0.0.0 bind 撞同址已监听端口(mock 子进程同样绑 0.0.0.0,生产行为一致)
        assert supervisor.port_in_use(busy)
        free = 9001 if busy != 9001 else 9002
        while supervisor.port_in_use(free):
            free += 1
        assert not supervisor.port_in_use(free)
    finally:
        s.close()


def test_alloc_free_port_skips_db_used(db_session):
    from app.models import MockInstance, Project
    p = Project(name="p-sup-1")
    db_session.add(p)
    db_session.commit()
    db_session.add(MockInstance(project_id=p.id, name="a", port=9001, token="x" * 32))
    db_session.commit()
    got = supervisor.alloc_free_port(db_session, "9001-9003")
    assert got in (9002, 9003)   # 9001 被库内预留
    # 范围耗尽/全被占 → ValueError;若本机恰好占用尾端口则跳过(环境抖动,非逻辑问题)
    for port in (9004, 9005):
        db_session.add(MockInstance(project_id=p.id, name="b", port=port, token="x" * 32))
    db_session.commit()
    try:
        got2 = supervisor.alloc_free_port(db_session, "9004-9006")
    except ValueError:
        pytest.skip("本机 9006 被外部占用")
    assert got2 == 9006


def test_start_stop_with_fake_child(monkeypatch, db_session):
    """不真 spawn:fake Popen+health/shutdown,验证状态机与 desired 迁移。"""
    from app.models import MockInstance, Project
    p = Project(name="p-sup-2")
    db_session.add(p)
    db_session.commit()
    inst = MockInstance(project_id=p.id, name="a", port=19031, token="t" * 32)
    db_session.add(inst)
    db_session.commit()

    calls = {"spawn": 0, "shutdown": 0}

    class FakeProc:
        def __init__(self):
            self.returncode = None
            self.terminated = False

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

        def terminate(self):
            self.terminated = True
            self.returncode = 0

    fake = FakeProc()

    def fake_popen(cmd, **kw):
        calls["spawn"] += 1
        return fake

    monkeypatch.setattr(supervisor.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(supervisor, "port_in_use", lambda port: False)
    monkeypatch.setattr(supervisor, "health_ok", lambda port, token, timeout=1.0: fake.returncode is None)
    monkeypatch.setattr(supervisor, "shutdown_orphan", lambda port, token: (calls.__setitem__("shutdown", calls["shutdown"] + 1) or True))

    status, msg = supervisor.start_instance(db_session, inst)
    assert status == "running" and inst.desired == "running" and calls["spawn"] == 1

    # 子进程死了 → 探活状态机标 error
    fake.returncode = 1
    supervisor._probe_once()
    db_session.expire_all()
    inst = db_session.get(MockInstance, inst.id)
    assert inst.status == "error" and "异常退出" in inst.error_message

    # stop:desired 翻转 + status 归 stopped
    supervisor.stop_instance(db_session, inst)
    assert inst.desired == "stopped" and inst.status == "stopped"

    # 已停实例再 start_port 空闲 → 重新 spawn
    fake.returncode = None
    status2, _ = supervisor.start_instance(db_session, inst)
    assert status2 == "running" and calls["spawn"] == 2


def test_reconcile_only_touches_desired_running(monkeypatch, db_session):
    from app.models import MockInstance, Project
    p = Project(name="p-sup-3")
    db_session.add(p)
    db_session.commit()
    db_session.add_all([
        MockInstance(project_id=p.id, name="run", port=19041, token="a" * 32, desired="running"),
        MockInstance(project_id=p.id, name="stop", port=19042, token="b" * 32, desired="stopped"),
    ])
    db_session.commit()
    seen = []

    def fake_start(db, inst):
        seen.append(inst.id)
        return "running", None

    monkeypatch.setattr(supervisor, "start_instance", fake_start)
    n = supervisor.reconcile(db_session)
    assert n == 1 and len(seen) == 1
