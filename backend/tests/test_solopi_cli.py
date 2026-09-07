# backend/tests/test_solopi_cli.py
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
