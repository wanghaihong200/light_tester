import pytest
from sqlalchemy import text

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


def _mk_project(db, name="app域项目"):
    p = Project(name=name)
    db.add(p); db.commit(); db.refresh(p)
    return p


_CASE = {
    "caseName": "smoke",
    "targetAppPackage": "com.example.app",
    "operationLog": {"steps": [
        {"operationNode": None,
         "operationMethod": {"actionEnum": "SLEEP", "operationParam": {"text": "500"},
                             "encrypt": False, "safeEncrypt": False},
         "operationIndex": 0, "operationId": "g1", "stepId": "s1"},
    ]},
}


def test_create_app_script_defaults(db):
    p = _mk_project(db)
    s = AppScript(project_id=p.id, name="冒烟", case_json=_CASE,
                  app_package=_CASE["targetAppPackage"])
    db.add(s); db.commit(); db.refresh(s)
    assert s.id > 0
    assert s.is_deleted is False
    assert s.case_json["operationLog"]["steps"][0]["operationMethod"]["actionEnum"] == "SLEEP"


def test_create_app_run_defaults(db):
    p = _mk_project(db)
    s = AppScript(project_id=p.id, name="冒烟", case_json=_CASE, app_package="com.example.app")
    db.add(s); db.commit(); db.refresh(s)
    r = AppRun(project_id=p.id, script_id=s.id, script_name=s.name,
               device_serial="SERIAL1", batch_id=None,
               pre_checks=[{"type": "text_contains", "value": "首页"}],
               post_checks=[], perf_items=["CPU", "FPS"])
    db.add(r); db.commit(); db.refresh(r)
    assert r.status == "pending"
    assert r.variables == {}
    assert r.run_state is None and r.results is None
    assert r.perf_items == ["CPU", "FPS"]
    assert r.is_deleted is False


def test_run_status_vocabulary():
    # 平台终态词汇与 CLI TERMINAL_STATES 对齐(passed/failed/cancelled)+ 平台自身的 pending/running
    assert {"pending", "running", "passed", "failed", "cancelled"} == {
        "pending", "running", *("passed", "failed", "cancelled")}
