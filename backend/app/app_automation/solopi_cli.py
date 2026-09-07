# app/app_automation/solopi_cli.py
"""solopi-ai CLI(Harness 分支 solopi-harness-cli 0.1.0)子进程薄封装。
事实源 = docs/superpowers/research/2026-09-07-plan12-solopi-prereq.md(勿凭记忆改协议):
- Windows 官方 sh launcher 不可用,统一 [sys.executable, -m, solopi_harness.solopi_ai, *全局项, <命令>, …];
- stdout 解析单个 JSON 对象(--pretty 仅影响缩进);退出码 0=成功 / 2=未就绪或终态失败 / 3=用法错 /
  4=ADB/HTTP/协议错 / 124=超时 / 130=中断;
- CLI 未安装抛 CliError("install"),端点层转 400(不 500)。"""
import importlib.util
import json
import subprocess
import sys

MODULE = ("-m", "solopi_harness.solopi_ai")


class CliError(RuntimeError):
    def __init__(self, stage: str, message: str, returncode: int = 4):
        super().__init__(message)
        self.stage = stage
        self.message = message
        self.returncode = returncode


_TERMINAL_STATES = ("passed", "failed", "cancelled")


def _has_terminal_run(payload: object) -> bool:
    """payload 是否携带终态 run 对象:嵌套 "run" 或顶层 state(与 executor._extract_run 同型)。
    仅用于 rc=2 的 run 载荷判别;CLI 其余 rc=2 提前返回(用例查询失败/插件缺失/已有回放运行)
    的载荷均无 terminal state,判别式安全(终审 C1 已逐分支核对)。"""
    if not isinstance(payload, dict):
        return False
    run = payload["run"] if isinstance(payload.get("run"), dict) else payload
    return run.get("state") in _TERMINAL_STATES


def cli_available() -> bool:
    return importlib.util.find_spec("solopi_harness") is not None


def _argv(cmd_args: list[str], serial: str | None = None) -> list[str]:
    argv = [sys.executable, *MODULE]
    if serial:
        argv += ["--serial", serial]
    return [*argv, "--pretty", *cmd_args]


def _call(cmd_args: list[str], serial: str | None = None, timeout: int = 180,
          accept_terminal_rc2: bool = False) -> dict:
    if not cli_available():
        raise CliError("install", "solopi-ai CLI 未安装:cd backend && source .venv/Scripts/activate && bash scripts/setup-solopi.sh", -1)
    try:
        p = subprocess.run(_argv(cmd_args, serial), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise CliError("timeout", f"CLI 超时({timeout}s): {' '.join(cmd_args[:2])}", 124) from e
    payload = None
    out = p.stdout.decode("utf-8", "replace")
    try:
        payload = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        pass
    if p.returncode == 0 and isinstance(payload, dict):
        return payload
    # 同步 run 以终态 failed/cancelled 结束时 CLI 退出码 2、完整 run JSON 在 stdout(终审 C1):
    # 这是业务失败不是环境失败,须把载荷交还 executor 收口(run_state/results 不能丢)。
    if p.returncode == 2 and accept_terminal_rc2 and _has_terminal_run(payload):
        return payload
    err = (p.stderr.decode("utf-8", "replace") or out).strip()[-300:]
    stage = {2: "device", 3: "usage", 4: "protocol", 124: "timeout"}.get(p.returncode, "unknown")
    raise CliError(stage, f"CLI {' '.join(cmd_args[:2])} 失败(rc={p.returncode}): {err}", p.returncode)


def doctor(serial: str) -> dict:
    return _call(["doctor"], serial=serial, timeout=60)


def list_cases(serial: str) -> dict:
    return _call(["cases"], serial=serial)


def case_validate(path: str, serial: str, confirm_high_risk: bool = False) -> dict:
    args = ["case-validate", "--file", path]
    if confirm_high_risk:
        args.append("--confirm-high-risk")
    return _call(args, serial=serial)


def case_import(path: str, serial: str, replace: bool = False, confirm_high_risk: bool = False) -> dict:
    args = ["case-import", "--file", path]
    if replace:
        args.append("--replace")
    if confirm_high_risk:
        args.append("--confirm-high-risk")
    return _call(args, serial=serial, timeout=300)


def run_case(case_name: str, serial: str, artifacts_dir: str, *,
             target_package: str | None = None, restart_app: bool | None = None,
             run_timeout: int = 600, confirm_high_risk: bool = False) -> dict:
    """阻塞回放:等终态并落 artifacts(result.json/screen.png/logcat.txt)。返回结果 JSON。"""
    args = ["run", "--case", case_name, "--artifacts", artifacts_dir,
            "--run-timeout", str(run_timeout)]
    if target_package:
        args += ["--target-package", target_package]
    if restart_app is True:
        args.append("--restart-app")
    elif restart_app is False:
        args.append("--no-restart-app")
    if confirm_high_risk:
        args.append("--confirm-high-risk")
    # 仅 run 放行 rc=2 终态载荷(failed/cancelled 是业务终态,非环境失败)
    return _call(args, serial=serial, timeout=run_timeout + 120, accept_terminal_rc2=True)


def result(run_id: str, serial: str) -> dict:
    return _call(["result", "--run-id", run_id], serial=serial)


def inspect(serial: str) -> dict:
    """控件树:{"success":…, "page": tree};节点字段 depth/className/nodeBound/text/description/
    resourceId/id/packageName/visible/type/children[](研究第 3 节)。"""
    return _call(["inspect"], serial=serial, timeout=60)


def screenshot(serial: str, output: str) -> dict:
    return _call(["screenshot", "--output", output], serial=serial, timeout=60)


def perf_list(serial: str) -> dict:
    return _call(["perf-list"], serial=serial)


def perf_start(serial: str, items: list[str], target_package: str | None = None) -> dict:
    # ⚠ --items 的分隔符按逗号实现;若 Task 17 冒烟实测 CLI 只认空格/重复 flag,只改这一行。
    args = ["perf-start", "--items", ",".join(items)]
    if target_package:
        args += ["--target-package", target_package]
    return _call(args, serial=serial, timeout=120)


def perf_stop(serial: str, session_id: str, output_dir: str) -> dict:
    return _call(["perf-stop", "--session-id", session_id, "--output", output_dir],
                 serial=serial, timeout=300)


def perf_analyze(input_dir: str) -> dict:
    return _call(["perf-analyze", "--input", input_dir], serial=None, timeout=120)


def startup_time(serial: str, package: str, mode: str = "cold", iterations: int = 3) -> dict:
    return _call(["startup-time", "--target-package", package, "--mode", mode,
                  "--iterations", str(iterations)], serial=serial, timeout=600)
