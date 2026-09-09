"""计划 14 Task 5:设备历史发现 + 导入端点(CLI 全 stub,不碰真机)。

对 brief 测试稿的仓内现状对齐(非行为偏离,断言点不变):
- _mk_project 实际签名 (client, headers, name=…)(同 tests/test_perf_records_api.py 注);
- solopi_perf 是顶层 app.solopi_perf(brief 误写 app.app_automation.solopi_perf,
  同 tests/test_perf_models.py 已注);
- solopi_harness CLI 在本 venv 已装(计划 12):perf_history_* / perf_analyze 任一不 stub
  都会起真子进程,record_perf_dir 不 stub 会写真 ../data/app/perf_records——与文件头
  「CLI 全 stub,不碰真机」冲突,故 brief 用例 2 的 stub 手法推广为 stub_history fixture
  供 4 用例共用(test 4 在 fixture 之上覆写 perf_history_get);
- 历史列表 stub 顺带带全 startTime/endTime/fileCount/sizeBytes/metrics:brief 稿仅含 id,
  不足以锁 Interfaces 节给前端 Task 10 的驼峰→蛇形映射契约;
- PerfRecordOut 既有 schema 无 source_ref 字段,按 brief 断言在 schemas.py 补可选字段。
"""
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from app import solopi_perf
from app.app_automation import solopi_cli
from app.config import settings
from app.database import SessionLocal
from app.models import PerfRecord

from tests.test_app_scripts_api import _admin_headers, _mk_project


@pytest.fixture(autouse=True)
def _clean_app_tables():
    """本文件写 perf_records 行;命名避开 conftest._clean_tables(同名会遮蔽,projects/users
    将不再被清理,同 tests/test_perf_records_api.py 注),顺带清 perf_records 落盘残留。"""
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
    for d in (Path(settings.app_data_dir) / "perf_records").glob("*"):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)


_HISTORY_GET = {
    "success": True, "kind": "performance", "id": "performance-abc",
    "startTime": 1725868800000, "endTime": 1725868860000,
    "metrics": ["CPU", "FPS"], "filesTruncated": False,
    "files": [{"fileName": "CPU_x_abc_0_0.csv", "preview": "ts,v\n0,1\n1,2\n"},
              {"fileName": "FPS_y_abc_1_0.csv", "preview": "ts,v\n0,30\n1,29\n"}],
}


@pytest.fixture
def stub_history(monkeypatch, tmp_path):
    """CLI 全 stub:历史列表/详情、perf-analyze(确定性统计)、落盘目录(→ tmp_path)。"""
    monkeypatch.setattr(solopi_cli, "perf_history_list",
                        lambda serial, limit=50: {"items": [{
                            "id": "performance-abc", "startTime": 1725868800000,
                            "endTime": 1725868860000, "fileCount": 2, "sizeBytes": 1234,
                            "metrics": ["CPU", "FPS"]}]})
    monkeypatch.setattr(solopi_cli, "perf_history_get",
                        lambda serial, history_id: dict(_HISTORY_GET))
    monkeypatch.setattr(solopi_cli, "perf_analyze",
                        lambda d: {"columns": [{"index": "CPU", "mean": 1.5}]})
    monkeypatch.setattr(solopi_perf, "record_perf_dir",
                        lambda rid: tmp_path / "perf_records" / str(rid))


def test_history_list_marks_imported(client, db_session, stub_history):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    r = client.post(f"/api/projects/{pid}/perf-records/import",
                    json={"serial": "dev1", "history_id": "performance-abc"}, headers=h)
    assert r.status_code == 201, r.text
    body = client.get("/api/app-devices/dev1/perf-history?limit=50", headers=h).json()
    item = body["items"][0]
    assert item["id"] == "performance-abc"
    assert item["start_time"] == 1725868800000 and item["end_time"] == 1725868860000
    assert item["file_count"] == 2 and item["size_bytes"] == 1234
    assert item["metrics"] == ["CPU", "FPS"]
    assert item["imported_record_id"] is not None


def test_import_creates_record_and_files(client, db_session, stub_history, tmp_path):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    r = client.post(f"/api/projects/{pid}/perf-records/import",
                    json={"serial": "dev1", "history_id": "performance-abc", "name": "手工采集"},
                    headers=h)
    assert r.status_code == 201, r.text
    row = r.json()
    assert row["source"] == "import" and row["source_ref"] == "performance-abc"
    assert row["data_complete"] is True and row["perf_items"] == ["CPU", "FPS"]
    assert row["perf_summary"]["columns"][0]["mean"] == 1.5
    # 采集起止=naive 本地时间(对齐 executor datetime.now() 惯例;带 UTC 序列化含 +00:00
    # 且语义偏 8 小时,前端直显即错位——计划14 终审修复锁定)
    assert row["started_at"] == datetime.fromtimestamp(1725868800).isoformat()
    assert row["finished_at"] == datetime.fromtimestamp(1725868860).isoformat()
    # preview 逐文件落盘到 record_perf_dir(stub → tmp_path),series 端点读同一目录
    saved = tmp_path / "perf_records" / str(row["id"]) / "CPU_x_abc_0_0.csv"
    assert saved.read_text(encoding="utf-8").startswith("ts,v")


def test_import_duplicate_conflicts(client, db_session, stub_history):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    body = {"serial": "dev1", "history_id": "performance-abc"}
    assert client.post(f"/api/projects/{pid}/perf-records/import", json=body,
                       headers=h).status_code == 201
    assert client.post(f"/api/projects/{pid}/perf-records/import", json=body,
                       headers=h).status_code == 409


def test_import_truncated_marks_incomplete(client, db_session, stub_history, monkeypatch):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)
    monkeypatch.setattr(solopi_cli, "perf_history_get",
                        lambda serial, history_id: {**_HISTORY_GET, "filesTruncated": True})
    r = client.post(f"/api/projects/{pid}/perf-records/import",
                    json={"serial": "dev1", "history_id": "performance-abc"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["data_complete"] is False


def test_import_save_failure_rolls_back(client, db_session, stub_history, monkeypatch, tmp_path):
    """落盘段异常回滚(计划14 终审):删行+清目录,不留空壳记录,响应 400 带原因。"""
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h)

    def _boom(record_id, files):
        solopi_perf.record_perf_dir(record_id).mkdir(parents=True, exist_ok=True)  # 模拟半落盘
        raise RuntimeError("disk full")

    monkeypatch.setattr(solopi_perf, "save_imported_csvs", _boom)
    r = client.post(f"/api/projects/{pid}/perf-records/import",
                    json={"serial": "dev1", "history_id": "performance-abc"}, headers=h)
    assert r.status_code == 400
    assert "导入落盘失败" in r.json()["detail"]
    assert db_session.query(PerfRecord).count() == 0  # 无空壳行
    assert list((tmp_path / "perf_records").glob("*")) == []  # 半落盘目录已清
