# backend/tests/test_solopi_cli.py
import json

import pytest

from app.app_automation import solopi_cli


class _FakeCompleted:
    def __init__(self, rc=0, stdout=b"{}", stderr=b""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def cli_ok(monkeypatch):
    monkeypatch.setattr(solopi_cli.importlib.util, "find_spec", lambda name: object())


def test_cli_unavailable_raises_install(monkeypatch):
    monkeypatch.setattr(solopi_cli.importlib.util, "find_spec", lambda name: None)
    with pytest.raises(solopi_cli.CliError) as ei:
        solopi_cli.doctor("s1")
    assert ei.value.stage == "install"
    assert ei.value.returncode == -1


def test_doctor_composes_argv_and_parses(cli_ok, monkeypatch):
    captured = {}

    def fake_run(argv, capture_output, timeout):
        captured["argv"], captured["timeout"] = argv, timeout
        return _FakeCompleted(stdout=b'{"success": true}')

    monkeypatch.setattr(solopi_cli.subprocess, "run", fake_run)
    assert solopi_cli.doctor("s1") == {"success": True}
    argv = captured["argv"]
    assert argv[:3] == [solopi_cli.sys.executable, "-m", "solopi_harness.solopi_ai"]
    assert argv[3:5] == ["--serial", "s1"]
    assert "--pretty" in argv and argv[-1] == "doctor"


def test_run_case_flags_and_timeout(cli_ok, monkeypatch):
    captured = {}

    def fake_run(argv, capture_output, timeout):
        captured["argv"], captured["timeout"] = argv, timeout
        return _FakeCompleted(stdout=b'{"run": {"state": "passed"}}')

    monkeypatch.setattr(solopi_cli.subprocess, "run", fake_run)
    solopi_cli.run_case("smoke", "s1", "C:/art", target_package="com.a",
                        restart_app=False, run_timeout=77, confirm_high_risk=True)
    argv = captured["argv"]
    i = argv.index("run")
    assert argv[i + 1:i + 7] == ["--case", "smoke", "--artifacts", "C:/art",
                                 "--run-timeout", "77"]
    assert argv[argv.index("--target-package") + 1] == "com.a"
    assert "--no-restart-app" in argv and "--confirm-high-risk" in argv
    assert captured["timeout"] == 77 + 120  # CLI 超时外留缓冲


def test_case_import_flags(cli_ok, monkeypatch):
    captured = {}

    def fake_run(argv, capture_output, timeout):
        captured["argv"] = argv
        return _FakeCompleted(stdout=b"{}")

    monkeypatch.setattr(solopi_cli.subprocess, "run", fake_run)
    solopi_cli.case_import("C:/c.json", "s1", replace=True, confirm_high_risk=True)
    argv = captured["argv"]
    i = argv.index("case-import")
    assert argv[i + 1:i + 7] == ["--file", "C:/c.json", "--replace", "--confirm-high-risk"]


def test_nonzero_rc_maps_stage(cli_ok, monkeypatch):
    monkeypatch.setattr(solopi_cli.subprocess, "run",
                        lambda *a, **k: _FakeCompleted(rc=2, stdout=b"", stderr=b"not ready"))
    with pytest.raises(solopi_cli.CliError) as ei:
        solopi_cli.list_cases("s1")
    assert ei.value.stage == "device" and ei.value.returncode == 2


def test_timeout_raises(cli_ok, monkeypatch):
    def boom(*a, **k):
        raise solopi_cli.subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(solopi_cli.subprocess, "run", boom)
    with pytest.raises(solopi_cli.CliError) as ei:
        solopi_cli.inspect("s1")
    assert ei.value.stage == "timeout" and ei.value.returncode == 124


def test_unparsable_stdout_rc0_raises(cli_ok, monkeypatch):
    monkeypatch.setattr(solopi_cli.subprocess, "run",
                        lambda *a, **k: _FakeCompleted(rc=0, stdout=b"not json"))
    with pytest.raises(solopi_cli.CliError):
        solopi_cli.list_cases("s1")


# ── 终审 C1:同步 run 以终态 failed/cancelled 结束时 CLI 退出码 2、完整 run JSON 在 stdout;
#    仅 run_case 放行(其余命令 rc=2 仍是环境失败),且要求载荷携带终态 run 对象 ──

_RC2_FAILED = {"run": {"state": "failed", "error": "ASSERT failed at step s2",
                       "results": [{"stepId": "s2", "status": "failed",
                                    "exceptionMessage": "断言失败", "exceptionStep": "ASSERT"}]}}


def _patch_rc(rc, stdout, stderr=b"cli error"):
    return lambda *a, **k: _FakeCompleted(rc=rc, stdout=stdout, stderr=stderr)


def test_run_case_accepts_rc2_terminal_payload(cli_ok, monkeypatch):
    body = json.dumps(_RC2_FAILED).encode("utf-8")
    monkeypatch.setattr(solopi_cli.subprocess, "run", _patch_rc(2, body))
    payload = solopi_cli.run_case("smoke", "s1", "C:/art")
    assert payload == _RC2_FAILED  # 业务失败的 run_state/results 不丢


def test_run_case_accepts_rc2_top_level_state(cli_ok, monkeypatch):
    body = json.dumps({"state": "cancelled", "error": "用户中断", "results": []}).encode("utf-8")
    monkeypatch.setattr(solopi_cli.subprocess, "run", _patch_rc(2, body))
    assert solopi_cli.run_case("smoke", "s1", "C:/art")["state"] == "cancelled"


def test_run_case_rc2_non_terminal_payload_still_raises(cli_ok, monkeypatch):
    # rc=2 但载荷无终态 state(如 duplicate_case / 设备未就绪)→ 照旧按环境失败抛
    body = json.dumps({"detail": "duplicate_case: already exists"}).encode("utf-8")
    monkeypatch.setattr(solopi_cli.subprocess, "run", _patch_rc(2, body))
    with pytest.raises(solopi_cli.CliError) as ei:
        solopi_cli.run_case("smoke", "s1", "C:/art")
    assert ei.value.stage == "device" and ei.value.returncode == 2


def test_run_case_rc4_terminal_payload_still_raises(cli_ok, monkeypatch):
    # 只有 rc==2 放行;rc=4 即使带终态载荷也是协议错
    body = json.dumps(_RC2_FAILED).encode("utf-8")
    monkeypatch.setattr(solopi_cli.subprocess, "run", _patch_rc(4, body))
    with pytest.raises(solopi_cli.CliError) as ei:
        solopi_cli.run_case("smoke", "s1", "C:/art")
    assert ei.value.stage == "protocol"


def test_other_calls_rc2_terminal_payload_still_raises(cli_ok, monkeypatch):
    # 放行仅限 run_case:case_import 等的 rc=2 不因载荷恰好带 state 被误放行
    body = json.dumps(_RC2_FAILED).encode("utf-8")
    monkeypatch.setattr(solopi_cli.subprocess, "run", _patch_rc(2, body))
    with pytest.raises(solopi_cli.CliError) as ei:
        solopi_cli.case_import("C:/c.json", "s1", replace=True)
    assert ei.value.stage == "device"


# ── 冒烟实测校正(2026-09-08):perf-start 的 argparse 要求 --target-package 与 --global
#    二选一必填,两者都缺 → usage error(rc=3);包名为空时须回退 --global(全局采集)──

def test_perf_start_without_package_falls_back_to_global(cli_ok, monkeypatch):
    captured = {}

    def fake_run(argv, capture_output, timeout):
        captured["argv"] = argv
        return _FakeCompleted(stdout=b'{"sessionId": "ps1"}')

    monkeypatch.setattr(solopi_cli.subprocess, "run", fake_run)
    solopi_cli.perf_start("s1", ["CPU"])
    argv = captured["argv"]
    assert "--global" in argv
    assert "--target-package" not in argv
    i = argv.index("perf-start")
    assert argv[i + 1:i + 3] == ["--items", "CPU"]


def test_perf_start_with_package_uses_target_package(cli_ok, monkeypatch):
    captured = {}

    def fake_run(argv, capture_output, timeout):
        captured["argv"] = argv
        return _FakeCompleted(stdout=b'{"sessionId": "ps1"}')

    monkeypatch.setattr(solopi_cli.subprocess, "run", fake_run)
    solopi_cli.perf_start("s1", ["CPU", "MEM"], target_package="com.a")
    argv = captured["argv"]
    assert "--global" not in argv
    assert argv[argv.index("--target-package") + 1] == "com.a"
    assert argv[argv.index("--items") + 1] == "CPU,MEM"
