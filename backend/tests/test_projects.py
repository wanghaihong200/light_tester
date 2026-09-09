import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal


@pytest.fixture()
def ah(client, db_session):
    """Task 5 存量用例补鉴权(保语义,补鉴权):bootstrap admin 登录头,admin 对所有项目直通。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(autouse=True)
def _clean_perf_rows():
    """test_delete_project_clears_perf_records 直插 perf_records 行;conftest._clean_tables
    不含该表,用例失败时残留行会以 uq_perf_source_ref 污染后续文件(同 test_perf_records_api
    的 _clean_app_tables 注),故模块内补位清理,顺带清 perf_records 落盘残留。"""
    yield
    s = SessionLocal()
    try:
        s.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        s.execute(text("TRUNCATE TABLE perf_records"))
        s.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        s.commit()
    finally:
        s.close()
    for d in (Path(settings.app_data_dir) / "perf_records").glob("*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


def test_create_and_get_project(client, ah):
    resp = client.post(
        "/api/projects", json={"name": "商城系统", "description": "被测系统A"}, headers=ah
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    resp = client.get(f"/api/projects/{pid}", headers=ah)
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "商城系统"
    assert "git_token" not in body  # 列表/详情不回显 token


def test_duplicate_name_rejected(client, ah):
    client.post("/api/projects", json={"name": "P"}, headers=ah)
    resp = client.post("/api/projects", json={"name": "P"}, headers=ah)
    assert resp.status_code == 409


def test_update_project(client, ah):
    pid = client.post("/api/projects", json={"name": "old"}, headers=ah).json()["id"]
    resp = client.put(
        f"/api/projects/{pid}",
        json={"name": "new", "git_repo_url": "http://gitlab.example/repo.git"},
        headers=ah,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new"


def test_delete_project(client, ah):
    pid = client.post("/api/projects", json={"name": "bye"}, headers=ah).json()["id"]
    assert client.delete(f"/api/projects/{pid}", headers=ah).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=ah).status_code == 404


def test_delete_project_clears_perf_records(client, ah, db_session):
    """项目删除连 perf_records(计划14 终审):perf_records.project_id FK RESTRICT,
    不清行删项目即 500;run/import 行全清,import 行连落盘目录(run 只删引用行)。"""
    from app import solopi_perf
    from app.models import PerfRecord

    pid = client.post("/api/projects", json={"name": "perf-clean"}, headers=ah).json()["id"]
    run_row = PerfRecord(project_id=pid, source="run", name="run行", script_name="s",
                         device_serial="dev1", perf_items=["CPU"], data_complete=True,
                         app_run_id=None, script_id=None, source_ref=None)
    import_row = PerfRecord(project_id=pid, source="import", name="导入行", script_name="",
                            device_serial="dev2", perf_items=["FPS"], data_complete=True,
                            app_run_id=None, script_id=None, source_ref="performance-x")
    db_session.add_all([run_row, import_row])
    db_session.commit()
    d = solopi_perf.record_perf_dir(import_row.id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "FPS.csv").write_text("ts,v\n0,1\n", encoding="utf-8")
    assert client.delete(f"/api/projects/{pid}", headers=ah).status_code == 204
    assert client.get(f"/api/projects/{pid}", headers=ah).status_code == 404
    db_session.expire_all()  # 删项目在端点自己的会话提交,清身份映射再计数
    assert db_session.query(PerfRecord).filter(PerfRecord.project_id == pid).count() == 0
    assert not d.exists()  # import 来源连数据目录,不留孤儿落盘


def test_rename_duplicate_name_409(client, ah):
    p1 = client.post("/api/projects", json={"name": "Alpha"}, headers=ah).json()["id"]
    client.post("/api/projects", json={"name": "Beta"}, headers=ah)
    resp = client.put(f"/api/projects/{p1}", json={"name": "Beta"}, headers=ah)
    assert resp.status_code == 409


def test_rename_fresh_name_200(client, ah):
    p1 = client.post("/api/projects", json={"name": "Alpha"}, headers=ah).json()["id"]
    resp = client.put(f"/api/projects/{p1}", json={"name": "Gamma"}, headers=ah)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Gamma"
