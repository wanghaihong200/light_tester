import pytest
from sqlalchemy import text

from app.app_automation import executor, solopi_cli
from app.database import SessionLocal
from app.models import AppRun, AppScript, Project


@pytest.fixture()
def db(db_session):
    """conftest 提供的是 db_session;这里起别名,使测试体与 plan 稿一致。"""
    return db_session


@pytest.fixture(autouse=True)
def _clean_app_tables():
    """conftest._TABLES 未包含 app_scripts/app_runs;若不清理,projects 被 TRUNCATE
    复位自增后 id 复用,残留行会挂在外键上卡住后续用例的项目删除(tests/test_projects.py)。"""
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


@pytest.fixture(autouse=True)
def _clear_force():
    executor._FORCE_FINISHED.clear()
    yield
    executor._FORCE_FINISHED.clear()


def test_notify_on_closed_loop_is_silent():
    """回归:上个测试文件经 main.py lifespan set_ui_loop 后,残留的 loop 已随
    TestClient 关闭;notify 对已关闭 loop 不得抛 RuntimeError,否则会被
    execute_app_run 的 except(RuntimeError)误判为环境失败把 run 判 failed。"""
    import asyncio

    from app.ui_automation import loopref

    prev = loopref.ui_loop()
    closed = asyncio.new_event_loop()
    closed.close()
    loopref.set_ui_loop(closed)
    try:
        executor.notify(1, {"type": "status"})
    finally:
        loopref.set_ui_loop(prev)  # 还原全局 loop,防污染后续用例


def _mk_run(db, status="pending") -> tuple[Project, AppRun]:
    p = Project(name=f"exec_{id(db)}")
    db.add(p); db.commit(); db.refresh(p)
    s = AppScript(project_id=p.id, name="冒烟",
                  case_json={"caseName": "smoke", "targetAppPackage": "com.example.app",
                             "operationLog": {"steps": [
                                 {"operationNode": None,
                                  "operationMethod": {"actionEnum": "SLEEP",
                                                      "operationParam": {"text": "500"},
                                                      "encrypt": False, "safeEncrypt": False},
                                  "operationIndex": 0, "operationId": "g1", "stepId": "s1"}]}})
    db.add(s); db.commit(); db.refresh(s)
    r = AppRun(project_id=p.id, script_id=s.id, script_name=s.name, device_serial="DEV1",
               pre_checks=[], post_checks=[], perf_items=[])
    db.add(r); db.commit(); db.refresh(r)
    return p, r


_OK_RUN = {"run": {"state": "passed", "error": None, "results": [{"stepId": "s1", "status": "passed"}]}}


@pytest.fixture
def happy_cli(monkeypatch):
    """全链路 happy path 的 CLI mock:import/run/inspect 均成功。"""
    monkeypatch.setattr(solopi_cli, "case_import", lambda *a, **k: {"success": True})
    monkeypatch.setattr(solopi_cli, "run_case", lambda *a, **k: dict(_OK_RUN))
    monkeypatch.setattr(solopi_cli, "inspect", lambda serial: {"success": True, "page": {
        "text": "", "children": [{"text": "首页", "resourceId": "com.example.app:id/home",
                                  "description": "", "children": []}]}})
    monkeypatch.setattr(solopi_cli, "perf_start", lambda *a, **k: {"sessionId": "ps1"})
    monkeypatch.setattr(solopi_cli, "perf_stop", lambda *a, **k: {"success": True})
    monkeypatch.setattr(solopi_cli, "perf_analyze", lambda *a, **k: {"columns": []})
    monkeypatch.setattr(solopi_cli, "startup_time", lambda *a, **k: {"samples": []})


def test_pass_flow_persists_terminal(db, monkeypatch, tmp_path, happy_cli):
    monkeypatch.setattr(executor.settings, "app_data_dir", tmp_path)
    _p, r = _mk_run(db)
    case = db.get(AppScript, r.script_id).case_json
    executor.execute_app_run(r.id, case, device_serial="DEV1", perf_items=[],
                             pre_checks=[], post_checks=[], include_startup=False,
                             allow_high_risk=False, app_package="com.example.app")
    # executor 在独立 Session 里提交;MySQL REPEATABLE READ 下本 session 事务不开新快照
    # 会读到提交前的旧值,须先结束事务再 expire_all 重读(brief 原文缺此行,按环境补)。
    db.rollback()
    db.expire_all()
    run = db.get(AppRun, r.id)
    assert run.status == "passed"
    assert run.run_state == "passed"
    assert run.results == _OK_RUN["run"]["results"]


def test_pre_check_failure_aborts_before_import(db, monkeypatch, tmp_path):
    monkeypatch.setattr(executor.settings, "app_data_dir", tmp_path)
    called = {}
    monkeypatch.setattr(solopi_cli, "inspect", lambda serial: {"success": True, "page": {"text": "主页", "children": []}})
    monkeypatch.setattr(solopi_cli, "case_import", lambda *a, **k: called.setdefault("imported", True))
    _p, r = _mk_run(db)
    case = db.get(AppScript, r.script_id).case_json
    executor.execute_app_run(r.id, case, device_serial="DEV1", perf_items=[],
                             pre_checks=[{"type": "text_contains", "value": "首页"}],
                             post_checks=[], include_startup=False,
                             allow_high_risk=False, app_package="com.example.app")
    # executor 在独立 Session 里提交;MySQL REPEATABLE READ 下本 session 事务不开新快照
    # 会读到提交前的旧值,须先结束事务再 expire_all 重读(brief 原文缺此行,按环境补)。
    db.rollback()
    db.expire_all()
    run = db.get(AppRun, r.id)
    assert run.status == "failed"
    assert "前置检查点未通过" in (run.error or "")
    assert "imported" not in called  # 前置失败不进入用例导入/执行


def test_business_failure_maps_failed(db, monkeypatch, tmp_path, happy_cli):
    monkeypatch.setattr(executor.settings, "app_data_dir", tmp_path)
    monkeypatch.setattr(solopi_cli, "run_case", lambda *a, **k: {
        "run": {"state": "failed", "error": "ASSERT failed at step s1",
                "results": [{"stepId": "s1", "status": "failed",
                             "exceptionMessage": "断言失败", "exceptionStep": "ASSERT"}]}})
    _p, r = _mk_run(db)
    case = db.get(AppScript, r.script_id).case_json
    executor.execute_app_run(r.id, case, device_serial="DEV1", perf_items=[],
                             pre_checks=[], post_checks=[], include_startup=False,
                             allow_high_risk=False, app_package="com.example.app")
    # executor 在独立 Session 里提交;MySQL REPEATABLE READ 下本 session 事务不开新快照
    # 会读到提交前的旧值,须先结束事务再 expire_all 重读(brief 原文缺此行,按环境补)。
    db.rollback()
    db.expire_all()
    run = db.get(AppRun, r.id)
    assert run.status == "failed"
    assert run.run_state == "failed"
    assert run.results[0]["exceptionStep"] == "ASSERT"


def test_env_failure_caught(db, monkeypatch, tmp_path, happy_cli):
    monkeypatch.setattr(executor.settings, "app_data_dir", tmp_path)

    def boom(*a, **k):
        raise solopi_cli.CliError("device", "设备未就绪", 2)

    monkeypatch.setattr(solopi_cli, "case_import", boom)
    _p, r = _mk_run(db)
    case = db.get(AppScript, r.script_id).case_json
    executor.execute_app_run(r.id, case, device_serial="DEV1", perf_items=[],
                             pre_checks=[], post_checks=[], include_startup=False,
                             allow_high_risk=False, app_package="com.example.app")
    # executor 在独立 Session 里提交;MySQL REPEATABLE READ 下本 session 事务不开新快照
    # 会读到提交前的旧值,须先结束事务再 expire_all 重读(brief 原文缺此行,按环境补)。
    db.rollback()
    db.expire_all()
    run = db.get(AppRun, r.id)
    assert run.status == "failed"
    assert "设备未就绪" in (run.error or "")


def test_force_finished_wins_over_late_result(db, monkeypatch, tmp_path, happy_cli):
    monkeypatch.setattr(executor.settings, "app_data_dir", tmp_path)
    _p, r = _mk_run(db)
    executor.mark_force_finished(r.id)
    case = db.get(AppScript, r.script_id).case_json
    executor.execute_app_run(r.id, case, device_serial="DEV1", perf_items=[],
                             pre_checks=[], post_checks=[], include_startup=False,
                             allow_high_risk=False, app_package="com.example.app")
    # executor 在独立 Session 里提交;MySQL REPEATABLE READ 下本 session 事务不开新快照
    # 会读到提交前的旧值,须先结束事务再 expire_all 重读(brief 原文缺此行,按环境补)。
    db.rollback()
    db.expire_all()
    run = db.get(AppRun, r.id)
    assert run.status == "cancelled"


def test_post_check_failure_downgrades_passed(db, monkeypatch, tmp_path):
    monkeypatch.setattr(executor.settings, "app_data_dir", tmp_path)
    monkeypatch.setattr(solopi_cli, "case_import", lambda *a, **k: {"success": True})
    monkeypatch.setattr(solopi_cli, "run_case", lambda *a, **k: dict(_OK_RUN))
    monkeypatch.setattr(solopi_cli, "inspect", lambda serial: {"success": True, "page": {"text": "别的主页", "children": []}})
    _p, r = _mk_run(db)
    case = db.get(AppScript, r.script_id).case_json
    executor.execute_app_run(r.id, case, device_serial="DEV1", perf_items=[],
                             pre_checks=[], post_checks=[{"type": "text_contains", "value": "首页"}],
                             include_startup=False, allow_high_risk=False, app_package="com.example.app")
    # executor 在独立 Session 里提交;MySQL REPEATABLE READ 下本 session 事务不开新快照
    # 会读到提交前的旧值,须先结束事务再 expire_all 重读(brief 原文缺此行,按环境补)。
    db.rollback()
    db.expire_all()
    run = db.get(AppRun, r.id)
    assert run.status == "failed"
    assert run.run_state == "passed"  # 端上终态与平台终态分开呈现
    assert "后置检查点未通过" in (run.error or "")
    assert run.check_results["post"][0]["passed"] is False
