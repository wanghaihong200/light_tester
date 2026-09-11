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
    """本文件直插 app_scripts/app_runs/perf_records 行;TRUNCATE 复位自增后 run id 跨
    pytest 会话复用,残留 CSV 会让 perf=False 的 run 误判有数据——落盘清理由
    conftest._isolate_app_data 承担(app_data_dir 指向临时目录,2026-09-10 事故后
    严禁测试清理真实 data/app,守卫见 test_app_data_dir_isolated_from_real)。"""
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


def test_app_data_dir_isolated_from_real():
    """守卫(2026-09-10 事故):并行 pytest 的清理 fixture 曾把真实 data/app/runs/*/perf
    rmtree 删光(用户冒烟数据被毁)。conftest._isolate_app_data 把 settings.app_data_dir
    指到会话临时目录——本测试先断言隔离生效(未隔离=指向真实相对路径即红),再在真实
    目录造哨兵、复刻事故清理形状跑一遍,哨兵必须安然无恙(证明无任何 fixture 会清真实
    目录)。哨兵本测试自建自清。"""
    real_app = (Path(__file__).resolve().parents[2] / "data" / "app").resolve()
    assert Path(settings.app_data_dir).resolve() != real_app
    sentinel_dir = real_app / "runs" / "sentinel_probe"
    sentinel = sentinel_dir / "x.csv"
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("ts,v\n0,1\n", encoding="utf-8")
    try:
        # 事故代码原形:清理 fixture 对 app_data_dir 下 runs/*/perf 做 rmtree
        for d in (Path(settings.app_data_dir) / "runs").glob("*/perf"):
            shutil.rmtree(d, ignore_errors=True)
        # 比事故更激进的形状:整棵 runs/* 都删——只要隔离生效,真实目录毫发无损
        for d in (Path(settings.app_data_dir) / "runs").glob("*"):
            shutil.rmtree(d, ignore_errors=True)
        assert sentinel.exists()
    finally:
        shutil.rmtree(sentinel_dir, ignore_errors=True)


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


def test_save_imported_csvs_writes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(solopi_perf, "record_perf_dir", lambda rid: tmp_path / str(rid))
    files = [
        {"fileName": "CPU_x_abc_0_0.csv", "preview": "ts,value\n0,1\n1,2\n"},
        {"fileName": "FPS.csv", "preview": ""},  # 空 preview 跳过
    ]
    n = solopi_perf.save_imported_csvs(7, files)
    assert n == 1
    saved = tmp_path / "7" / "CPU_x_abc_0_0.csv"
    assert saved.read_text(encoding="utf-8").startswith("ts,value")
    assert solopi_perf.has_valid_perf_csv(tmp_path / "7") is True


def test_save_imported_csvs_skips_non_dict_and_sanitizes_name(tmp_path, monkeypatch):
    """计划 14 Task 5 顺手硬化(Task2 deferred minor):非 dict 项跳过(不抛
    AttributeError);文件名路径分隔符归一,a/b.csv 落盘为 a_b.csv 而非建子目录。"""
    monkeypatch.setattr(solopi_perf, "record_perf_dir", lambda rid: tmp_path / str(rid))
    files = [{"fileName": "a/b.csv", "preview": "x\n"}, "not-a-dict", None]
    n = solopi_perf.save_imported_csvs(8, files)
    assert n == 1
    assert (tmp_path / "8" / "a_b.csv").read_text(encoding="utf-8") == "x\n"
    assert not (tmp_path / "8" / "a").exists() and not (tmp_path / "8" / "b.csv").exists()


def test_save_imported_csvs_reads_text_from_preview_dict(tmp_path, monkeypatch):
    """真机 perf-history-get 的 files[].preview 是 dict({charset, fileName, modifiedAt,
    pathAvailable, relativePath, sizeBytes, text, truncated}),CSV 文本在 text 键——此前
    当字符串 write_text 直接报 "data must be str, not dict"(2026-09-10 冒烟)。
    文件级 truncated=True 的文件照样落盘(截断感知是 router 职责,置 data_complete=False);
    text 为空的文件跳过;字符串 preview(旧桩)兼容由上一用例锁定。"""
    monkeypatch.setattr(solopi_perf, "record_perf_dir", lambda rid: tmp_path / str(rid))
    name = "CPU温度_Temperature_6f1c725f5fab3cd4_1789045016565_1789045048339.csv"
    files = [
        {"fileName": name,
         "preview": {"charset": "GBK", "fileName": name, "modifiedAt": 1789045016565,
                     "pathAvailable": True, "relativePath": name, "sizeBytes": 1024,
                     "truncated": False,
                     "text": "RecordTime,CPU温度(度),extra,SimpleTime\n1789,42.8,null,0.457\n"}},
        {"fileName": "FPS_x_abc_1_0.csv",  # 文件级截断:照样落盘
         "preview": {"charset": "GBK", "text": "ts,v\n0,30\n1,29\n", "truncated": True}},
        {"fileName": "empty.csv",
         "preview": {"charset": "GBK", "text": "", "truncated": False}},  # 空 text 跳过
    ]
    n = solopi_perf.save_imported_csvs(9, files)
    assert n == 2
    saved = tmp_path / "9" / name
    assert saved.read_text(encoding="utf-8").startswith("RecordTime,CPU温度(度)")
    assert (tmp_path / "9" / "FPS_x_abc_1_0.csv").read_text(encoding="utf-8").startswith("ts,v")
    assert not (tmp_path / "9" / "empty.csv").exists()
