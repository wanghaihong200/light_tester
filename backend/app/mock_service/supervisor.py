"""Mock 实例进程管理:端口分配/启停/开机对账/探活(声明式 desired,ADR-0009)。"""
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

from app.config import settings
from app.database import SessionLocal
from app.models import MockInstance

HEALTH_WAIT_SECONDS = 5.0
PROBE_INTERVAL_SECONDS = 10.0

_procs: dict[int, subprocess.Popen] = {}
_probe_task: asyncio.Task | None = None


def parse_port_range(spec: str) -> tuple[int, int]:
    try:
        lo, hi = spec.split("-")
        lo, hi = int(lo), int(hi)
    except (ValueError, AttributeError):
        raise ValueError(f"mock_port_range 格式非法: {spec!r}(应如 9001-9499)")
    if lo <= 0 or hi < lo or hi > 65535:
        raise ValueError(f"mock_port_range 范围非法: {spec!r}")
    return lo, hi


def bind_ok(port: int) -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def port_in_use(port: int) -> bool:
    return not bind_ok(port)


def alloc_free_port(db, spec: str | None = None) -> int:
    lo, hi = parse_port_range(spec or settings.mock_port_range)
    used = {row[0] for row in db.query(MockInstance.port).all()}  # 含软删行=端口预留
    for p in range(lo, hi + 1):
        if p not in used and bind_ok(p):
            return p
    raise ValueError(f"端口范围 {lo}-{hi} 内无可用端口")


def health_ok(port: int, token: str, timeout: float = 1.0) -> bool:
    try:
        return httpx.get(f"http://127.0.0.1:{port}/__mock_health__",
                         params={"token": token}, timeout=timeout).status_code == 200
    except httpx.HTTPError:
        return False


def shutdown_orphan(port: int, token: str) -> bool:
    try:
        return httpx.post(f"http://127.0.0.1:{port}/__mock_shutdown__",
                          params={"token": token}, timeout=2.0).status_code == 200
    except httpx.HTTPError:
        return False


def child_log_path(instance_id: int) -> Path:
    log_dir = settings.mock_data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"{instance_id}.log"


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]   # app/mock_service/supervisor.py → backend/


def start_instance(db, instance) -> tuple[str, str | None]:
    proc = _procs.get(instance.id)
    if proc is not None and proc.poll() is None:
        instance.desired = instance.status = "running"
        instance.error_message = None
        return "running", None
    if port_in_use(instance.port):
        if health_ok(instance.port, instance.token):
            # 自己的活实例(句柄丢失,如平台重启后未对账)→ 直接认领
            instance.desired = instance.status = "running"
            instance.error_message = None
            return "running", None
        if shutdown_orphan(instance.port, instance.token):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and port_in_use(instance.port):
                time.sleep(0.2)
        if port_in_use(instance.port):
            instance.desired = "running"
            instance.status = "error"
            msg = f"端口 {instance.port} 被外部进程占用"
            instance.error_message = msg
            return "error", msg
    instance.desired = "running"
    instance.status = "starting"
    db.commit()
    log = open(child_log_path(instance.id), "ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.mock_service.app",
         "--instance-id", str(instance.id), "--parent-pid", str(os.getpid())],
        cwd=_backend_root(), stdout=subprocess.DEVNULL, stderr=log)
    _procs[instance.id] = proc
    deadline = time.monotonic() + HEALTH_WAIT_SECONDS
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        if health_ok(instance.port, instance.token, timeout=0.5):
            instance.status = "running"
            instance.error_message = None
            return "running", None
        time.sleep(0.2)
    if proc.poll() is not None:
        instance.status = "error"
        msg = f"mock 进程启动即退出 code={proc.returncode},日志 {child_log_path(instance.id)}"
    else:
        instance.status = "error"
        msg = f"健康检查超时({HEALTH_WAIT_SECONDS}s),日志 {child_log_path(instance.id)}"
    instance.error_message = msg
    return "error", msg


def stop_instance(db, instance) -> None:
    instance.desired = "stopped"
    proc = _procs.pop(instance.id, None)
    if shutdown_orphan(instance.port, instance.token):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and health_ok(instance.port, instance.token, timeout=0.5):
            time.sleep(0.2)
    if proc is not None and proc.poll() is None:
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    instance.status = "stopped"
    instance.error_message = None


def reconcile(db) -> int:
    n = 0
    rows = (db.query(MockInstance)
            .filter(MockInstance.desired == "running", MockInstance.is_deleted.is_(False)).all())
    for inst in rows:
        start_instance(db, inst)
        n += 1
    db.commit()
    return n


async def _probe_loop() -> None:
    while True:
        await asyncio.sleep(PROBE_INTERVAL_SECONDS)
        try:
            _probe_once()
        except Exception:
            continue  # 探活绝不炸平台


def _probe_once() -> None:
    with SessionLocal() as db:
        rows = (db.query(MockInstance)
                .filter(MockInstance.desired == "running", MockInstance.is_deleted.is_(False)).all())
        for inst in rows:
            proc = _procs.get(inst.id)
            if proc is not None and proc.poll() is not None:
                inst.status = "error"
                inst.error_message = f"mock 进程异常退出 code={proc.returncode},日志 {child_log_path(inst.id)}"
                _procs.pop(inst.id, None)
                continue
            if health_ok(inst.port, inst.token):
                if inst.status != "running":
                    inst.status = "running"
                    inst.error_message = None
            elif inst.status == "running":
                inst.status = "error"
                inst.error_message = "健康探测失败(mock 无响应)"
        db.commit()


def start_probe_task() -> None:
    global _probe_task
    if _probe_task is None:
        _probe_task = asyncio.create_task(_probe_loop())


def stop_probe_task() -> None:
    global _probe_task
    if _probe_task is not None:
        _probe_task.cancel()
        _probe_task = None


def shutdown_all() -> None:
    for instance_id in list(_procs):
        proc = _procs.pop(instance_id)
        if proc.poll() is None:
            proc.terminate()
