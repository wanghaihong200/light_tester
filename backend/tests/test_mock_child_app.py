"""子进程 mock 服务:命中/兜底/延迟/超时/CORS/健康关停/命中落库滚动。"""
import time

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.mock_service.app import HIT_KEEP_PER_INSTANCE, create_mock_app
from app.models import MockHit, MockInstance, MockRule, Project


def _setup(db: Session, *, port=19011, cors=False, rule_kwargs=None, **inst_kw) -> MockInstance:
    p = Project(name=f"p-child-{port}")
    db.add(p)
    db.commit()
    inst = MockInstance(project_id=p.id, name="svc", port=port, token="tok" + "0" * 29,
                        cors_enabled=cors, **inst_kw)
    db.add(inst)
    db.commit()
    if rule_kwargs:
        # sort_order 允许被 rule_kwargs 覆盖(test_conditions 用例显式传 sort_order=0)
        db.add(MockRule(instance_id=inst.id, **{"sort_order": 0, **rule_kwargs}))
        db.commit()
    return inst


def _client(db: Session, inst: MockInstance) -> TestClient:
    # 不做 db.expire_all():expire 后首次访问 inst.id 会触发刷新读,在 MySQL REPEATABLE READ
    # 下开启一个先于请求提交的快照事务,后续命中断言将永远读到旧快照(NoResultFound)。
    # 应用侧每请求自建 SessionLocal 实时读库,本 session 无缓存需要失效。
    return TestClient(create_mock_app(inst.id))


def test_exact_rule_hit_and_template_echo(db_session):
    inst = _setup(db_session, rule_kwargs=dict(
        method="POST", path_template="/users/{id}", enable_template=True,
        response_body='{"id": "{{ path.id }}", "name": "{{ jpath(\'$.name\') }}"}'))
    with _client(db_session, inst) as c:
        r = c.post("/users/42", json={"name": "王"})
    assert r.status_code == 200
    assert r.json() == {"id": "42", "name": "王"}
    hit = db_session.query(MockHit).filter_by(instance_id=inst.id).one()
    assert hit.matched is True and hit.response_status == 200
    assert hit.request_body is not None and "王" in hit.request_body


def test_miss_serves_default_response_and_logs(db_session):
    inst = _setup(db_session)  # 无规则
    with _client(db_session, inst) as c:
        r = c.get("/nope", params={"a": "1"})
    assert r.status_code == 404
    assert r.json() == {"error": "no mock rule matched"}
    hit = db_session.query(MockHit).filter_by(instance_id=inst.id).one()
    assert hit.matched is False and hit.rule_id is None and hit.query == "a=1"


def test_conditions_gate_and_order_first_match_wins(db_session):
    inst = _setup(db_session, rule_kwargs=dict(
        method="GET", path_template="/pay", sort_order=0,
        conditions=[{"scope": "query", "key": "mode", "match": "eq", "value": "fail"}],
        response_status=500, response_body='{"code":"FAIL"}'))
    db_session.add(MockRule(instance_id=inst.id, sort_order=1, method="GET",
                            path_template="/pay", response_status=200, response_body='{"code":"OK"}'))
    db_session.commit()
    with _client(db_session, inst) as c:
        assert c.get("/pay", params={"mode": "fail"}).status_code == 500
        ok = c.get("/pay", params={"mode": "ok"})
    assert ok.status_code == 200 and ok.json() == {"code": "OK"}


def test_delay_and_timeout_hold(db_session):
    inst = _setup(db_session, rule_kwargs=dict(method="GET", path_template="/slow",
                                               delay_ms=300, response_body="ok"))
    with _client(db_session, inst) as c:
        t0 = time.monotonic()
        assert c.get("/slow").status_code == 200
        assert time.monotonic() - t0 >= 0.25
    db_session.expire_all()
    hit = db_session.query(MockHit).filter_by(instance_id=inst.id).one()
    assert hit.delay_ms == 300


def test_timeout_simulated_marks_error_field(db_session):
    inst = _setup(db_session, rule_kwargs=dict(method="GET", path_template="/hang",
                                               timeout_enabled=True, timeout_seconds=1))
    with _client(db_session, inst) as c:
        r = c.get("/hang")   # 测试里挂 1s 后照常返回;生产语义=客户端先超时
    assert r.status_code == 200
    db_session.expire_all()
    hit = db_session.query(MockHit).filter_by(instance_id=inst.id).one()
    assert hit.error == "timeout-simulated"


def test_cors_preflight_bypasses_rules_and_normal_headers(db_session):
    inst = _setup(db_session, cors=True)
    with _client(db_session, inst) as c:
        pre = c.options("/anything", headers={"Origin": "http://x", "Access-Control-Request-Method": "POST"})
        assert pre.status_code == 204
        assert pre.headers["access-control-allow-origin"] == "*"
        assert db_session.query(MockHit).filter_by(instance_id=inst.id).count() == 0  # 预检不记
        normal = c.get("/anything")
    assert normal.headers.get("access-control-allow-origin") == "*"


def test_health_and_shutdown_token(db_session):
    inst = _setup(db_session)
    with _client(db_session, inst) as c:
        assert c.get("/__mock_health__", params={"token": inst.token}).status_code == 200
        assert c.get("/__mock_health__", params={"token": "bad"}).status_code == 403
        assert c.post("/__mock_shutdown__", params={"token": inst.token}).status_code == 200


def test_hit_retention_rolls_at_limit(db_session):
    inst = _setup(db_session)
    with _client(db_session, inst) as c:
        for _ in range(HIT_KEEP_PER_INSTANCE + 5):
            c.get("/x")
    ids = [row[0] for row in db_session.query(MockHit.id)
           .filter_by(instance_id=inst.id).order_by(MockHit.id.asc()).all()]
    assert len(ids) == HIT_KEEP_PER_INSTANCE
    assert ids[0] == 6   # 最旧 5 条被淘汰


def test_instance_removed_serves_404(db_session):
    inst = _setup(db_session)
    app = create_mock_app(inst.id + 100000)  # 不存在的实例
    with TestClient(app) as c:
        assert c.get("/x").status_code == 404


def test_oversized_and_binary_body_hit_still_served(db_session):
    inst = _setup(db_session)  # 无规则
    with _client(db_session, inst) as c:
        r = c.post("/upload", content=bytes(range(256)) * 300)  # ≈76,800 字节,大量非法 utf-8
    assert r.status_code == 404  # 大体/二进制不把 mock 打成 500
    assert r.json() == {"error": "no mock rule matched"}
    hit = db_session.query(MockHit).filter_by(instance_id=inst.id).one()
    assert hit.request_body
    assert len(hit.request_body.encode("utf-8")) <= 65535  # TEXT 容量(65,535 字节)内


def test_real_subprocess_end_to_end(db_session):
    """真 spawn 一例子进程:supervisor 启动 → 真端口命中 → 停止。走真实 DB(test 库)。"""
    from app.mock_service import supervisor

    p = Project(name="p-child-real")
    db_session.add(p)
    db_session.commit()
    inst = MockInstance(project_id=p.id, name="real", port=9499, token="real" + "0" * 28)
    db_session.add(inst)
    db_session.commit()
    db_session.add(MockRule(instance_id=inst.id, method="GET", path_template="/hi",
                            response_status=200, response_body="hello"))
    db_session.commit()
    try:
        status, msg = supervisor.start_instance(db_session, inst)
        assert status == "running", msg
        r = httpx.get("http://127.0.0.1:9499/hi", timeout=3)
        assert r.status_code == 200 and r.text == "hello"
        supervisor.stop_instance(db_session, inst)
        assert inst.status == "stopped"
    finally:
        supervisor.shutdown_all()
