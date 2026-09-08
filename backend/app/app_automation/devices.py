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
# 手机 App 回放列表「导出用例」实际写入目录(FileUtils.getSubDir("export"),真机实测):
# harness-import 只是 HarnessSchemeResolver(PC CLI case-import 推送)的写入目录,与 App 导出无关。
SOLOPI_EXPORT_DIR = "/sdcard/solopi/export"

_CASE_SOURCES = ((HARNESS_IMPORT_DIR, "harness"), (SOLOPI_EXPORT_DIR, "export"))


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


def list_device_cases(serial: str, remote_dir: str | None = None) -> list[dict]:
    """列出设备上录制导出的用例 JSON(只列文件名,不拉内容);目录不存在/为空返回 []。
    默认扫两目录:harness-import(PC CLI 推送)+ /sdcard/solopi/export(App「导出用例」),
    每条带 source 标明来源;同名文件两目录都有时两条都返回,按 (file_name, source) 排序。
    显式传 remote_dir(?dir= 覆盖,见前置研究修正 #3)只扫该目录,source 归 harness(调试通道)。
    ?dir= 会拼进 adb shell 参数、在设备端 sh 里执行,目录须过白名单防注入(终审 I1);
    不匹配抛 RuntimeError(路由 except 转 400)。"""
    if remote_dir is not None:
        dirs = ((remote_dir, "harness"),)
    else:
        dirs = _CASE_SOURCES
    out: list[dict] = []
    for d, source in dirs:
        if not re.fullmatch(r"[/A-Za-z0-9_.\- ]+", d):
            raise RuntimeError(f"非法目录: {d}")
        p = subprocess.run(["adb", "-s", serial, "shell", "ls", f"{d}/*.json"],
                           capture_output=True, timeout=30)
        for ln in p.stdout.decode("utf-8", "replace").splitlines():
            ln = ln.strip()
            if ln.endswith(".json") and "No such file" not in ln:
                out.append({"file_name": ln.rsplit("/", 1)[-1], "source": source})
    return sorted(out, key=lambda r: (r["file_name"], r["source"]))


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
