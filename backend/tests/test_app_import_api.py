"""Task 8(计划 12):用例导入双通道(设备拉取/文件上传)+ 设备与 perf 项端点 API 测试。

对 brief 样例的仓内现状对齐(非行为偏离):
- _admin_headers 需带 db_session(Task 7 已提交签名 _admin_headers(client, db_session));
- 补 db_session 入参 + autouse TRUNCATE app_scripts/app_runs 清理(conftest._TABLES 未含该表,
  同 tests/test_app_scripts_api.py 的 _clean_app_tables);
- 顺手项(Task 7 评审遗留,非强制):补「非成员访问 app-scripts(含导入/设备面)→ 404」用例,
  复用 tests.test_app_scripts_api 的 _auth 同型 helper。"""

import json

import pytest
from sqlalchemy import text

from app.app_automation import devices as app_devices
from app.app_automation import solopi_cli
from app.database import SessionLocal

from tests.test_app_scripts_api import _CASE, _admin_headers, _auth, _mk_project


@pytest.fixture
def device_env(monkeypatch, tmp_path):
    """无真机:mock 设备清单/文件列表/拉取;app_data_dir 指向临时目录(拉取落盘不污染真实数据目录)。"""
    from app.config import settings

    monkeypatch.setattr(settings, "app_data_dir", tmp_path)
    monkeypatch.setattr(app_devices, "list_devices_detailed",
                        lambda: [{"serial": "DEV1", "state": "device"},
                                 {"serial": "DEV2", "state": "unauthorized"}])
    monkeypatch.setattr(app_devices, "list_device_cases",
                        lambda serial, remote_dir=None:
                            [{"file_name": "case_a.json", "source": "harness"},
                             {"file_name": "case_b.json", "source": "export"}])

    def fake_pull(serial, file_name, dest, remote_dir=app_devices.HARNESS_IMPORT_DIR):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(_CASE), encoding="utf-8")
        return dest

    monkeypatch.setattr(app_devices, "pull_device_case", fake_pull)
    return tmp_path


@pytest.fixture(autouse=True)
def _clean_app_tables():
    """本文件会写 app_scripts 行;conftest._TABLES 未含该表,projects 被 TRUNCATE 复位自增后
    id 复用,残留行会串项目污染全量回归(清理方式同 tests/test_app_scripts_api.py)。"""
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


def test_list_device_cases_endpoint(client, device_env, db_session):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "导入项目")
    r = client.get(f"/api/projects/{pid}/app-scripts/device-cases?serial=DEV1", headers=h)
    assert r.status_code == 200
    assert r.json() == [{"file_name": "case_a.json", "source": "harness"},
                        {"file_name": "case_b.json", "source": "export"}]


class _Completed:
    def __init__(self, stdout=b"", stderr=b"", rc=0):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def test_list_device_cases_scans_both_dirs(monkeypatch):
    """真机实测校正:App「导出用例」写 /sdcard/solopi/export,推送通道写 harness-import,
    默认扫两目录各带 source;?dir= 显式覆盖仍只扫该目录(白名单防注入不变)。"""
    captured: list = []

    def fake_run(argv, capture_output, timeout):
        captured.append(argv)
        return _Completed(stdout=b"/sdcard/x/case_a.json\n")

    monkeypatch.setattr(app_devices.subprocess, "run", fake_run)
    assert app_devices.list_device_cases("DEV1") == [
        {"file_name": "case_a.json", "source": "export"},
        {"file_name": "case_a.json", "source": "harness"},
    ]
    assert captured[0][-1] == f"{app_devices.HARNESS_IMPORT_DIR}/*.json"
    assert captured[1][-1] == f"{app_devices.SOLOPI_EXPORT_DIR}/*.json"
    captured.clear()
    assert app_devices.list_device_cases("DEV1", "/sdcard/harness files/v2") == [
        {"file_name": "case_a.json", "source": "harness"}]
    assert captured[-1][-1] == "/sdcard/harness files/v2/*.json"


def test_list_device_cases_dir_whitelist(monkeypatch):
    """终审 I1:?dir= 直通 adb shell,在设备端 sh 里执行,须白名单校验防注入。"""
    captured: list = []

    def fake_run(argv, capture_output, timeout):
        captured.append(argv)
        return _Completed(stdout=b"/sdcard/x/case_a.json\n")

    monkeypatch.setattr(app_devices.subprocess, "run", fake_run)
    # 合法目录放行:默认双目录 / 含空格短横线的自定义目录
    assert len(app_devices.list_device_cases("DEV1")) == 2
    assert captured[0][-1] == f"{app_devices.HARNESS_IMPORT_DIR}/*.json"
    captured.clear()
    assert app_devices.list_device_cases("DEV1", "/sdcard/harness files/v2") == [
        {"file_name": "case_a.json", "source": "harness"}]
    # 注入载荷被拒且不触达 adb(路由层 except 转 400)
    captured.clear()
    with pytest.raises(RuntimeError):
        app_devices.list_device_cases("DEV1", "y; reboot; ")
    assert not captured


def test_device_cases_endpoint_rejects_injected_dir(client, db_session):
    """终审 I1 端到端:?dir= 注入载荷被白名单拦下,路由 except 转 400(用真实现,不走 device_env mock)。"""
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "注入项目")
    r = client.get(f"/api/projects/{pid}/app-scripts/device-cases?serial=DEV1&dir=y%3B%20reboot%3B%20",
                   headers=h)
    assert r.status_code == 400
    assert "设备读取失败" in r.json()["detail"]


def test_import_device_creates_script(client, device_env, db_session):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "拉取项目")
    r = client.post(f"/api/projects/{pid}/app-scripts/import-device", headers=h,
                    json={"serial": "DEV1", "file_name": "case_a.json"})
    assert r.status_code == 201, r.text
    assert r.json()["case_json"]["caseName"] == "下单冒烟"
    # 拉取文件落盘在 app_data_dir/imports(留痕排查用;device_env 已把 app_data_dir 指到 tmp_path)
    assert (device_env / "imports" / "case_a.json").exists()


def test_import_device_source_export_pulls_solopi_dir_and_unwraps(client, device_env, db_session,
                                                                  monkeypatch):
    """真机实测校正:App「导出用例」写 /sdcard/solopi/export 且是 RecordCaseInfo 包装结构
    (operationLog 为内嵌 JSON 字符串)。source=export 须按该目录 pull,且落库前剥包装过原生校验。"""
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "App导出拉取项目")
    wrapped = {"id": 3, "caseName": "App导出用例", "caseDesc": "回放列表导出",
               "targetAppPackage": "com.example.app", "targetAppLabel": "示例",
               "recordMode": 1, "advanceSettings": {}, "priority": 0,
               "gmtCreate": "2026-09-08 10:00:00", "gmtModify": "2026-09-08 10:00:00",
               "selected": False, "storePath": "/sdcard/solopi/store/x",
               "operationLog": json.dumps({"steps": _CASE["operationLog"]["steps"],
                                           "storePath": "/sdcard/solopi/store/x"})}
    captured: dict = {}

    def fake_pull(serial, file_name, dest, remote_dir=app_devices.HARNESS_IMPORT_DIR, **kw):
        captured["remote_dir"] = remote_dir
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(wrapped), encoding="utf-8")
        return dest

    monkeypatch.setattr(app_devices, "pull_device_case", fake_pull)
    r = client.post(f"/api/projects/{pid}/app-scripts/import-device", headers=h,
                    json={"serial": "DEV1", "file_name": "export_case.json", "source": "export"})
    assert r.status_code == 201, r.text
    assert captured["remote_dir"] == app_devices.SOLOPI_EXPORT_DIR
    cj = r.json()["case_json"]
    assert isinstance(cj["operationLog"]["steps"], list) and cj["operationLog"]["steps"]
    for bad in ("id", "gmtCreate", "gmtModify", "selected", "storePath"):
        assert bad not in cj
    assert cj["caseName"] == "App导出用例"


def test_import_device_source_invalid_400(client, device_env, db_session):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "来源校验项目")
    r = client.post(f"/api/projects/{pid}/app-scripts/import-device", headers=h,
                    json={"serial": "DEV1", "file_name": "case_a.json", "source": "bogus"})
    assert r.status_code == 400 and "source" in r.json()["detail"]


def test_import_device_high_risk_gate(client, device_env, db_session, monkeypatch):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "拉取高危项目")
    risky = json.loads(json.dumps(_CASE))
    risky["operationLog"]["steps"][0]["operationMethod"]["actionEnum"] = "KILL_PROCESS"

    def pull_risky(serial, file_name, dest, remote_dir=app_devices.HARNESS_IMPORT_DIR):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(risky), encoding="utf-8")
        return dest

    monkeypatch.setattr(app_devices, "pull_device_case", pull_risky)
    r = client.post(f"/api/projects/{pid}/app-scripts/import-device", headers=h,
                    json={"serial": "DEV1", "file_name": "risky.json"})
    assert r.status_code == 400 and "高危" in r.json()["detail"]
    r2 = client.post(f"/api/projects/{pid}/app-scripts/import-device", headers=h,
                     json={"serial": "DEV1", "file_name": "risky.json", "allow_high_risk": True})
    assert r2.status_code == 201


def test_import_upload_endpoint(client, device_env, db_session):
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "上传项目")
    r = client.post(f"/api/projects/{pid}/app-scripts/import-upload", headers=h,
                    files={"file": ("up.json", json.dumps(_CASE), "application/json")},
                    data={"name": "上传的用例"})
    assert r.status_code == 201
    assert r.json()["name"] == "上传的用例"
    # 非法 JSON 400
    r2 = client.post(f"/api/projects/{pid}/app-scripts/import-upload", headers=h,
                     files={"file": ("bad.json", b"not json", "application/json")})
    assert r2.status_code == 400
    # 超限 400(>1MB)
    big = b"x" * (1024 * 1024 + 1)
    r3 = client.post(f"/api/projects/{pid}/app-scripts/import-upload", headers=h,
                     files={"file": ("big.json", big, "application/json")})
    assert r3.status_code == 400


def test_app_devices_endpoint(client, device_env, db_session):
    h = _admin_headers(client, db_session)
    r = client.get("/api/app-devices", headers=h)
    assert r.status_code == 200
    assert {d["serial"] for d in r.json()} == {"DEV1", "DEV2"}


def test_app_device_perf_items(client, db_session, monkeypatch):
    """冒烟实测校正(2026-09-08):perf-list 响应键确认为 items,但每项是对象
    {"key": "CPU", "name": …, "permissions": […]};端点须提取 key 字段返回字符串数组,
    而非 str(dict) 出的 "{'key': 'CPU', …}" 垃圾串。"""
    monkeypatch.setattr(solopi_cli, "perf_list", lambda serial: {"items": [
        {"key": "CPU", "name": "CPU", "permissions": ["adb"], "tip": "", "trigger": ""},
        {"key": "FPS", "name": "FPS", "permissions": [], "tip": "", "trigger": ""},
    ]})
    h = _admin_headers(client, db_session)
    r = client.get("/api/app-devices/DEV1/perf-items", headers=h)
    assert r.status_code == 200, r.text
    assert r.json() == {"items": ["CPU", "FPS"]}


def test_app_device_perf_items_fallback_shapes(client, db_session, monkeypatch):
    """兜底语义:键名回退(metrics/keys)+ 非字典项兜底 str + dict 缺 key 过滤。"""
    h = _admin_headers(client, db_session)
    monkeypatch.setattr(solopi_cli, "perf_list", lambda serial: {"metrics": ["MEM", {"key": "NET"}]})
    r = client.get("/api/app-devices/DEV1/perf-items", headers=h)
    assert r.json() == {"items": ["MEM", "NET"]}
    monkeypatch.setattr(solopi_cli, "perf_list", lambda serial: {"keys": [{"name": "无 key"}]})
    r2 = client.get("/api/app-devices/DEV1/perf-items", headers=h)
    assert r2.json() == {"items": []}  # dict 无 key 时过滤,不吐 "None"


def test_non_member_gets_404(client, db_session, make_user):
    """Task 7 评审顺手项:非成员访问 app-scripts(列表/导入/设备面)= 404 不泄漏存在性。"""
    h = _admin_headers(client, db_session)
    pid = _mk_project(client, h, "隔离项目")
    outsider = _auth(client, db_session, make_user, "appoutsider")
    assert client.get(f"/api/projects/{pid}/app-scripts", headers=outsider).status_code == 404
    assert client.get(f"/api/projects/{pid}/app-scripts/device-cases?serial=DEV1",
                      headers=outsider).status_code == 404
    assert client.post(f"/api/projects/{pid}/app-scripts/import-device", headers=outsider,
                       json={"serial": "DEV1", "file_name": "case_a.json"}).status_code == 404
