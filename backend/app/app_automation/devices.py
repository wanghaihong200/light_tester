"""设备清单与 per-device 锁 + 录制导出拉取。
锁模式仿 ui_automation/nodepath.TARGET_LOCKS(BoundedSemaphore(1)),key 从「端」细化为 adb serial;
占用即 409 不排队。多设备仅支持 USB(SoloPi 官方:Wi-Fi 连不了多台)。"""
import re
import subprocess
import threading
from pathlib import Path

_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

_locks_guard = threading.Lock()
DEVICE_LOCKS: dict[str, threading.BoundedSemaphore] = {}

HARNESS_IMPORT_DIR = "/sdcard/Android/data/com.alipay.hulu/files/harness-import"


def lock_for(serial: str) -> threading.BoundedSemaphore:
    with _locks_guard:
        return DEVICE_LOCKS.setdefault(serial, threading.BoundedSemaphore(1))


def list_devices_detailed() -> list[dict]:
    """adb devices → [{serial, state}];保留非 device 态行(前端据此提示未授权设备)。"""
    p = subprocess.run(["adb", "devices"], capture_output=True, timeout=30)
    rows = []
    for ln in p.stdout.decode("utf-8", "replace").splitlines()[1:]:
        parts = ln.split("\t")
        if len(parts) == 2 and parts[0].strip():
            rows.append({"serial": parts[0].strip(), "state": parts[1].strip()})
    return rows


def list_device_cases(serial: str, remote_dir: str = HARNESS_IMPORT_DIR) -> list[dict]:
    """列出设备上录制导出的用例 JSON(只列文件名,不拉内容);目录不存在/为空返回 []。"""
    p = subprocess.run(["adb", "-s", serial, "shell", "ls", f"{remote_dir}/*.json"],
                       capture_output=True, timeout=30)
    names = []
    for ln in p.stdout.decode("utf-8", "replace").splitlines():
        ln = ln.strip()
        if ln.endswith(".json") and "No such file" not in ln:
            names.append(ln.rsplit("/", 1)[-1])
    return [{"file_name": n} for n in sorted(names)]


def pull_device_case(serial: str, file_name: str, dest: Path, remote_dir: str = HARNESS_IMPORT_DIR) -> Path:
    """adb pull 单个用例文件到平台侧 dest;文件名白名单防路径穿越。"""
    if not _NAME_RE.fullmatch(file_name) or file_name in (".", ".."):
        raise RuntimeError(f"非法文件名: {file_name}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(["adb", "-s", serial, "pull", f"{remote_dir}/{file_name}", str(dest)],
                       capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"adb pull 失败: {p.stderr.decode('utf-8', 'replace').strip()[:200]}")
    return dest
