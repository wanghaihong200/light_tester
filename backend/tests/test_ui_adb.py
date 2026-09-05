# tests/test_ui_adb.py
import subprocess
from pathlib import Path

import pytest

from app.ui_automation import adb


def _fake_run(calls, *, outputs=None):
    """替换 subprocess.run:记录 argv,按 outputs 弹出 stdout(bytes)。"""
    def fake(args, **kw):
        calls.append(args)
        out = (outputs or [b"ok"]).pop(0)
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr=b"")
    return fake


def test_collect_app_data_writes_tar_and_rejects_tiny(monkeypatch, tmp_path):
    calls: list = []
    monkeypatch.setattr(adb.subprocess, "run", _fake_run(calls, outputs=[b"x" * 4096]))
    dest = tmp_path / "s.tar"
    adb.collect_app_data("com.demo.app", dest)
    assert dest.read_bytes() == b"x" * 4096
    assert calls[0][:4] == ["adb", "exec-out", "run-as", "com.demo.app"]
    assert "tar" in calls[0] and "-cf" in calls[0]
    monkeypatch.setattr(adb.subprocess, "run", _fake_run([], outputs=[b"tiny"]))
    with pytest.raises(RuntimeError, match="快照过小"):
        adb.collect_app_data("com.demo.app", tmp_path / "t.tar")


def test_restore_sequence(monkeypatch, tmp_path):
    calls: list = []
    tar = tmp_path / "s.tar"; tar.write_bytes(b"x" * 4096)
    monkeypatch.setattr(adb.subprocess, "run", _fake_run(calls))
    adb.restore_app_data("com.demo.app", tar)
    joined = [" ".join(c) for c in calls]
    assert any("push" in j and "tc_snap.tar" in j for j in joined)
    assert any("run-as com.demo.app tar -xf" in j for j in joined)
    assert any("am force-stop com.demo.app" in j for j in joined)
    assert any("monkey -p com.demo.app" in j for j in joined)


def test_list_devices_parses_state(monkeypatch):
    out = ("List of devices attached\nserialA\tdevice\nserialB\toffline\n\n").encode()
    monkeypatch.setattr(adb.subprocess, "run", _fake_run([], outputs=[out]))
    assert adb.list_devices() == ["serialA"]


def test_check_adb_failure(monkeypatch):
    def boom(args, **kw):
        return subprocess.CompletedProcess(args, 1, stdout=b"", stderr=b"adb: not found")
    monkeypatch.setattr(adb.subprocess, "run", boom)
    with pytest.raises(RuntimeError):
        adb.check_adb()


# ---------- API 测试(全 mock adb,不发真子进程) ----------

def _admin_headers(client):
    # 照抄 tests/test_ui_scripts_api.py 的 bootstrap admin 登录取 token 模式
    from app.bootstrap import ensure_bootstrap_admin
    from app.database import SessionLocal as SL

    db = SL()
    try:
        ensure_bootstrap_admin(db)
    finally:
        db.close()
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_android_snapshot_api_creates_and_filters(client, monkeypatch, tmp_path):
    ah = _admin_headers(client)
    pid = client.post("/api/projects", json={"name": "android-snap"}, headers=ah).json()["id"]
    # 快照文件写进临时目录,不污染真实 ../data/ui
    from app.config import settings
    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)
    monkeypatch.setattr(adb, "check_adb", lambda: "Android Debug Bridge version 1.0.41")
    monkeypatch.setattr(adb, "list_devices", lambda: ["serialA"])
    monkeypatch.setattr(adb, "collect_app_data",
                        lambda package, dest: dest.write_bytes(b"x" * 4096))

    r = client.post(f"/api/projects/{pid}/ui-auth-states/android-snapshot",
                    json={"name": "抖音登录态", "app_package": "com.ss.android.ugc.aweme"}, headers=ah)
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "android_snapshot"
    assert body["app_package"] == "com.ss.android.ugc.aweme"
    # storage_path 不外泄(UiAuthStateOut 口径);改验文件确实落在 ui_data_dir/auth/android 下
    assert "storage_path" not in body
    tars = list((tmp_path / "auth" / "android").glob("*.tar"))
    assert len(tars) == 1 and tars[0].read_bytes() == b"x" * 4096

    # kind 筛选:android_snapshot 命中,web_storage 为空;不传 kind 保持原行为全量返回
    lst = client.get(f"/api/projects/{pid}/ui-auth-states", params={"kind": "android_snapshot"}, headers=ah).json()
    assert [x["id"] for x in lst] == [body["id"]]
    assert client.get(f"/api/projects/{pid}/ui-auth-states",
                      params={"kind": "web_storage"}, headers=ah).json() == []
    assert [x["id"] for x in client.get(f"/api/projects/{pid}/ui-auth-states", headers=ah).json()] == [body["id"]]

    # 非法包名 422(pydantic pattern 闸门)
    assert client.post(f"/api/projects/{pid}/ui-auth-states/android-snapshot",
                       json={"name": "坏包名", "app_package": "not a package"}, headers=ah).status_code == 422


def test_android_snapshot_api_conflict_paths(client, monkeypatch, tmp_path):
    """409 三路:adb 不可用 / 无在线设备 / 采集失败(失败须回滚不留孤儿行)。"""
    from app.config import settings
    ah = _admin_headers(client)
    pid = client.post("/api/projects", json={"name": "android-409"}, headers=ah).json()["id"]
    monkeypatch.setattr(settings, "ui_data_dir", tmp_path)

    monkeypatch.setattr(adb, "check_adb",
                        lambda: (_ for _ in ()).throw(RuntimeError("adb: command not found")))
    r = client.post(f"/api/projects/{pid}/ui-auth-states/android-snapshot",
                    json={"name": "n", "app_package": "com.demo.app"}, headers=ah)
    assert r.status_code == 409 and "adb 不可用" in r.json()["detail"]

    monkeypatch.setattr(adb, "check_adb", lambda: "ok")
    monkeypatch.setattr(adb, "list_devices", lambda: [])
    r = client.post(f"/api/projects/{pid}/ui-auth-states/android-snapshot",
                    json={"name": "n", "app_package": "com.demo.app"}, headers=ah)
    assert r.status_code == 409 and "无在线 Android 设备" in r.json()["detail"]

    monkeypatch.setattr(adb, "list_devices", lambda: ["serialA"])
    monkeypatch.setattr(adb, "collect_app_data",
                        lambda package, dest: (_ for _ in ()).throw(RuntimeError("快照过小:应用可能不可调试")))
    r = client.post(f"/api/projects/{pid}/ui-auth-states/android-snapshot",
                    json={"name": "n", "app_package": "com.demo.app"}, headers=ah)
    assert r.status_code == 409 and "快照采集失败" in r.json()["detail"]
    # 失败即回滚:不留 storage_path 为空的孤儿行
    assert client.get(f"/api/projects/{pid}/ui-auth-states", headers=ah).json() == []
