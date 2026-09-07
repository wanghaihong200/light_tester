"""Task 10(计划 12):运行数据端点测试——分发批量对比矩阵 + perf 曲线序列。

对 brief 样例的仓内现状对齐(非行为偏离,断言点不变):
- _admin_headers 实际签名是 (client, db_session)(Task 7 落地形态),各用例补 db_session 入参;
- 补 db 别名 fixture + autouse TRUNCATE app_runs/app_scripts 清理(conftest._TABLES 未含,
  本文件直插脚本与 run 行,同 tests/test_app_models.py,不清会污染全量回归)。"""

import pytest
from sqlalchemy import text

from app.database import SessionLocal
from app.models import AppRun, AppScript, Project

from tests.test_app_scripts_api import _admin_headers, _mk_project


@pytest.fixture()
def db(db_session):
    """conftest 提供的是 db_session;这里起别名,使测试体与 plan 稿一致。"""
    return db_session


@pytest.fixture(autouse=True)
def _clean_app_tables():
    """本文件直插 app_runs/app_scripts 行;conftest._TABLES 未含这两表,projects 被 TRUNCATE
    复位自增后 id 复用,残留行会串项目污染全量回归(清理方式同 tests/test_app_models.py)。"""
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


def _mk_batch(db, pid) -> tuple[int, str]:
    p = db.get(Project, pid)
    s = AppScript(project_id=pid, name="对比", case_json={
        "caseName": "cmp", "targetAppPackage": "com.a",
        "operationLog": {"steps": [
            {"operationNode": None,
             "operationMethod": {"actionEnum": "SLEEP", "operationParam": {"text": "1"},
                                 "encrypt": False, "safeEncrypt": False},
             "operationIndex": 0, "operationId": "g", "stepId": "s"}]}})
    db.add(s); db.commit(); db.refresh(s)
    batch = "batch123"
    db.add_all([
        AppRun(project_id=pid, script_id=s.id, script_name=s.name, device_serial="DEV-2", batch_id=batch,
               status="passed", run_state="passed",
               perf_summary={"columns": [{"index": "CPU", "mean": 12.5}]}, startup_summary=None,
               pre_checks=[], post_checks=[], perf_items=["CPU"]),
        AppRun(project_id=pid, script_id=s.id, script_name=s.name, device_serial="DEV-1", batch_id=batch,
               status="failed", run_state="failed", error="ASSERT failed",
               pre_checks=[], post_checks=[], perf_items=[]),
    ])
    db.commit()
    return s.id, batch


def test_comparison_matrix(client, db, db_session):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "对比项目")
    _sid, batch = _mk_batch(db, pid)
    r = client.get(f"/api/projects/{pid}/app-runs/comparison?batch_id={batch}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["batch_id"] == batch and body["script_name"] == "对比"
    assert [row["device_serial"] for row in body["runs"]] == ["DEV-1", "DEV-2"]  # 按序列号排序
    assert body["runs"][1]["perf_summary"]["columns"][0]["mean"] == 12.5
    # 未知 batch → 404
    r2 = client.get(f"/api/projects/{pid}/app-runs/comparison?batch_id=none", headers=h)
    assert r2.status_code == 404


def test_perf_series(client, db, db_session, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "曲线项目")
    sid, _ = _mk_batch(db, pid)
    run = db.query(AppRun).filter(AppRun.script_id == sid).first()
    perf_dir = tmp_path / "runs" / str(run.id) / "perf"
    perf_dir.mkdir(parents=True)
    (perf_dir / "CPU.csv").write_bytes("时间,CPU(%)\n10:00,12.5\n10:01,18.0\n".encode("gbk"))

    r = client.get(f"/api/app-runs/{run.id}/perf-series", headers=h)
    assert r.status_code == 200
    series = r.json()["series"]
    assert len(series) == 1
    assert series[0]["item"] == "CPU"
    assert series[0]["rows"] == [["10:00", "12.5"], ["10:01", "18.0"]]
    # 无 perf 的 run → 空数组(DEV-1 那行未采集)
    other = db.query(AppRun).filter(AppRun.script_id == sid, AppRun.device_serial == "DEV-1").first()
    r2 = client.get(f"/api/app-runs/{other.id}/perf-series", headers=h)
    assert r2.json()["series"] == []
