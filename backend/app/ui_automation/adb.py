# app/ui_automation/adb.py
"""adb 子进程薄封装(Android 应用数据快照)。仅标准库;adb 需在 PATH。
前置:Android 6+(toybox tar)且被测 app 为可调试包(run-as 可用),否则对应函数抛 RuntimeError。"""
import subprocess
from pathlib import Path

_TMP_TAR = "/data/local/tmp/tc_snap.tar"


def _run(args: list[str], *, timeout: int = 120) -> bytes:
    p = subprocess.run(["adb", *args], capture_output=True, timeout=timeout)
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").strip()[:200]
        raise RuntimeError(f"adb {' '.join(args[:3])} 失败: {err}")
    return p.stdout


def check_adb() -> str:
    out = _run(["version"]).decode("utf-8", "replace")
    return out.splitlines()[0]


def list_devices() -> list[str]:
    out = _run(["devices"]).decode("utf-8", "replace").splitlines()[1:]
    return [ln.split("\t")[0] for ln in out
            if ln.strip() and ln.split("\t")[-1].strip() == "device"]


def collect_app_data(package: str, dest: Path) -> None:
    """run-as 进入应用私有目录打 tar(run-as 默认 cwd 即 /data/data/<pkg>)。"""
    data = _run(["exec-out", "run-as", package, "tar", "-cf", "-", "."], timeout=300)
    if len(data) < 512:
        raise RuntimeError("快照过小:应用可能不可调试(需 debug 包)或数据目录为空")
    dest.write_bytes(data)


def restore_app_data(package: str, tar_path: Path) -> None:
    """回推并解开快照,重启应用使数据生效;失败抛 RuntimeError(由执行线程转环境级失败)。"""
    _run(["push", str(tar_path), _TMP_TAR], timeout=300)
    _run(["shell", "run-as", package, "tar", "-xf", _TMP_TAR], timeout=300)
    _run(["shell", "rm", "-f", _TMP_TAR])
    stop_app(package)
    launch_app(package)


def stop_app(package: str) -> None:
    _run(["shell", "am", "force-stop", package])


def launch_app(package: str) -> None:
    _run(["shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"])
