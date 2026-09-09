"""计划 14 Task 1:PerfRecord 模型 + run 引用行登记服务。
conftest._TABLES 未含 perf_records/app_runs/app_scripts,本文件自带清理(仓库模式)。

对 brief 测试稿的两处环境对齐(非行为偏离,断言点不变):
- _mk_run 直插 AppRun 前先建 Project/AppScript(MySQL InnoDB 外键真实约束,
  对齐 tests/test_app_executor.py::_mk_run 的仓库模式);
- register_run_perf_record 在独立 Session 提交,断言前须 rollback+expire_all 结束本
  session 事务重开快照(MySQL REPEATABLE READ,同 test_app_executor 既有注释模式);
- 清理 fixture 命名 _clean_app_tables(与 conftest._clean_tables 同名会遮蔽,
  projects 等表将不再被清理,见 test_app_run_data.py 同款注释)。"""

import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from app import solopi_perf  # brief 测试稿误写 app.app_automation.solopi_perf;以 brief Files/Step3 的 app/solopi_perf.py 顶层模块为准
from app.config import settings
from app.database import SessionLocal
from app.models import AppRun, AppScript, PerfRecord, Project


@pytest.fixture(autouse=True)
def _clean_app_tables():
    """本文件直插 app_scripts/app_runs/perf_records 行;顺带清 runs/*/perf——TRUNCATE
    复位自增后 run id 跨 pytest 会话复用,残留 CSV 会让 perf=False 的 run 误判有数据。"""
    yield
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for t in ("perf_records", "app_runs", "app_scripts"):
            session.execute(text(f"TRUNCATE TABLE {t}"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        session.commit()
    finally:
        session.close()
    for d in (Path(settings.app_data_dir) / "runs").glob("*/perf"):
        shutil.rmtree(d, ignore_errors=True)


def _mk_run(db, *, status="passed", perf=True):
    p = Project(name=f"perf_{uuid4().hex[:8]}")
    db.add(p); db.commit(); db.refresh(p)
    s = AppScript(project_id=p.id, name="s", case_json={
        "caseName": "s", "targetAppPackage": "com.example.app",
        "operationLog": {"steps": [
            {"operationNode": None,
             "operationMethod": {"actionEnum": "SLEEP", "operationParam": {"text": "1"},
                                 "encrypt": False, "safeEncrypt": False},
             "operationIndex": 0, "operationId": "g", "stepId": "s"}]}})
    db.add(s); db.commit(); db.refresh(s)
    run = AppRun(project_id=p.id, script_id=s.id, script_name="s", device_serial="dev1",
                 status=status, perf_items=["CPU"] if perf else [],
                 started_at=None, finished_at=None)
    db.add(run)
    db.commit()
    db.refresh(run)
    if perf:  # 造有效 perf CSV(≥2 行数据)
        d = solopi_perf.run_perf_dir(run.id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "CPU.csv").write_text("ts,value\n0,10\n1,20\n", encoding="utf-8")
    return run


def test_register_run_creates_reference_row(db_session):
    run = _mk_run(db_session, status="passed")
    solopi_perf.register_run_perf_record(run.id)
    db_session.rollback(); db_session.expire_all()
    row = db_session.query(PerfRecord).one()
    assert row.source == "run" and row.app_run_id == run.id
    assert row.project_id == run.project_id and row.script_name == "s"
    assert row.data_complete is True and row.perf_items == ["CPU"]


def test_register_is_idempotent(db_session):
    run = _mk_run(db_session)
    solopi_perf.register_run_perf_record(run.id)
    solopi_perf.register_run_perf_record(run.id)
    db_session.rollback(); db_session.expire_all()
    assert db_session.query(PerfRecord).count() == 1


def test_register_skips_cancelled_and_empty(db_session):
    cancelled = _mk_run(db_session, status="cancelled")
    empty = _mk_run(db_session, status="failed", perf=False)
    noperf = _mk_run(db_session, status="passed", perf=False)
    solopi_perf.register_run_perf_record(cancelled.id)
    solopi_perf.register_run_perf_record(empty.id)
    solopi_perf.register_run_perf_record(noperf.id)
    db_session.rollback(); db_session.expire_all()
    assert db_session.query(PerfRecord).count() == 0


def test_executor_source_has_hooks():
    import inspect
    from app.app_automation import executor
    src = inspect.getsource(executor)
    assert src.count("register_run_perf_record(") >= 2  # 成功终态 + env 失败两处
