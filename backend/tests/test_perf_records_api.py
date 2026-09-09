"""计划 14 Task 3:perf_records CRUD + 统一 series API(权限/双来源目录解析)。

对 brief 测试稿的仓内现状对齐(非行为偏离,断言点不变):
- solopi_perf 是顶层 app.solopi_perf(brief 误写 app.app_automation.solopi_perf,
  同 tests/test_perf_models.py 已注);_mk_project 实际签名 (client, headers, name=…);
- 权限两用例复用 tests/test_app_scripts_api.py 的 _auth 同型 helper(源自
  tests/test_jobs_repo_isolation.py;brief 指的 test_auth_enforcement.py 里无成员构造 helper):
  viewer GET→200、DELETE→403,editor DELETE→200,非成员 GET→404(permissions.py:非成员 404、
  角色不足 403、admin 直通 owner);
- _mk_run 直插 AppRun 前先建 AppScript(app_runs.script_id 是真 FK,同 test_perf_models 模式);
- 清理 fixture 命名 _clean_app_tables(同名 _clean_tables 会遮蔽 conftest 的,projects/users
  将不再被清理,同 test_perf_models.py 注),顺带清 runs/*/perf 与 perf_records/* 残留 CSV
  (TRUNCATE 复位自增后 id 复用,残留文件会污染 series 断言)。
"""
import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

from app import solopi_perf
from app.config import settings
from app.database import SessionLocal
from app.models import AppRun, AppScript, PerfRecord

from tests.test_app_scripts_api import _admin_headers, _auth, _mk_project


@pytest.fixture(autouse=True)
def _clean_app_tables():
    yield
    s = SessionLocal()
    try:
        s.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for t in ("perf_records", "app_runs", "app_scripts"):
            s.execute(text(f"TRUNCATE TABLE {t}"))
        s.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        s.commit()
    finally:
        s.close()
    data = Path(settings.app_data_dir)
    for d in (data / "runs").glob("*/perf"):
        shutil.rmtree(d, ignore_errors=True)
    for d in (data / "perf_records").glob("*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


_SCRIPT_CASE = {
    "caseName": "s", "targetAppPackage": "com.example.app",
    "operationLog": {"steps": [
        {"operationNode": None,
         "operationMethod": {"actionEnum": "SLEEP", "operationParam": {"text": "1"},
                             "encrypt": False, "safeEncrypt": False},
         "operationIndex": 0, "operationId": "g", "stepId": "s"}]}}


def _mk_record(db, *, project_id=1, source="import", name="导入记录", **kw):
    fields = dict(project_id=project_id, source=source, name=name, script_name="s",
                  device_serial="dev1", perf_items=["CPU"], data_complete=True,
                  script_id=None, app_run_id=None,
                  source_ref="performance-abc" if source == "import" else None)
    fields.update(kw)
    row = PerfRecord(**fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _mk_run(db, pid):
    """AppRun 直插前置 AppScript(app_runs.script_id 真 FK,MySQL InnoDB 真实约束)。"""
    s = AppScript(project_id=pid, name="s", case_json=_SCRIPT_CASE)
    db.add(s); db.commit(); db.refresh(s)
    run = AppRun(project_id=pid, script_id=s.id, script_name="s", device_serial="dev1",
                 status="passed")
    db.add(run); db.commit(); db.refresh(run)
    return run


def test_list_and_filters(client, db_session):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    _mk_record(db_session, project_id=pid)
    _mk_record(db_session, project_id=pid, source="run", source_ref=None, name="run行")
    body = client.get(f"/api/projects/{pid}/perf-records", headers=h).json()
    assert len(body) == 2
    body = client.get(f"/api/projects/{pid}/perf-records?source=run", headers=h).json()
    assert len(body) == 1 and body[0]["source"] == "run"


def test_series_resolves_import_dir(client, db_session):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    rec = _mk_record(db_session, project_id=pid)
    d = solopi_perf.record_perf_dir(rec.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "CPU.csv").write_text("ts,v\n0,1\n1,2\n", encoding="utf-8")
    body = client.get(f"/api/perf-records/{rec.id}/series", headers=h).json()
    assert body["record"]["id"] == rec.id  # series 端点契约含 record(前端 Task 8 消费)
    assert body["series"][0]["item"] == "CPU" and len(body["series"][0]["rows"]) == 2


def test_series_resolves_run_dir(client, db_session):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    run = _mk_run(db_session, pid)
    rec = _mk_record(db_session, project_id=pid, source="run", app_run_id=run.id,
                     script_id=run.script_id, source_ref=None, name="run行")
    d = solopi_perf.run_perf_dir(run.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "CPU.csv").write_text("ts,v\n0,1\n1,2\n", encoding="utf-8")
    body = client.get(f"/api/perf-records/{rec.id}/series", headers=h).json()
    assert body["series"][0]["item"] == "CPU"


def test_delete_import_removes_dir(client, db_session):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    rec = _mk_record(db_session, project_id=pid)
    d = solopi_perf.record_perf_dir(rec.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "CPU.csv").write_text("a\n", encoding="utf-8")
    r = client.delete(f"/api/perf-records/{rec.id}", headers=h)
    assert r.status_code == 200 and not d.exists()


def test_viewer_can_read_editor_can_delete(client, db_session, make_user):
    """权限:viewer GET→200、DELETE→403(角色不足);editor DELETE→200。
    成员构造复用 test_app_scripts_api._auth 同型 helper(建号密码 pw-<name>)。"""
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    rec = _mk_record(db_session, project_id=pid)
    vh = _auth(client, db_session, make_user, "perfviewer", project_ids=[pid], role="viewer")
    assert client.get(f"/api/perf-records/{rec.id}", headers=vh).status_code == 200
    assert client.delete(f"/api/perf-records/{rec.id}", headers=vh).status_code == 403
    eh = _auth(client, db_session, make_user, "perfeditor", project_ids=[pid], role="editor")
    assert client.delete(f"/api/perf-records/{rec.id}", headers=eh).status_code == 200


def test_non_member_gets_404(client, db_session, make_user):
    """可见性先行:非项目成员 GET 记录→404,不泄漏存在性(permissions.py 404 优先于 403)。"""
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    rec = _mk_record(db_session, project_id=pid)
    oh = _auth(client, db_session, make_user, "perfoutsider")  # 不加入任何项目
    assert client.get(f"/api/perf-records/{rec.id}", headers=oh).status_code == 404
