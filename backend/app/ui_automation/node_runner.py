# app/ui_automation/node_runner.py
"""Node 子进程执行器(spawn-per-run):job.json 入参,stdout NDJSON 事件流。
事件 schema 与 SSE 执行事件一致;done 事件携带 usage/report_path 供 ai_usage 落库。
退出语义:发过 done=受控结束;未发 done 即退出=崩溃(抛 RuntimeError 由线程转环境级失败);
watchdog 轮询 runner.is_force_finished,命中即 kill 并安静返回(状态已由 force-finish 接口落库)。"""
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from app.config import settings

_POLL_SEC = 1.0


def _write_job(run_id: int, run_dir: Path, doc: dict, *, driver_target: str, mode: str,
               variables: dict | None, storage_state: str | None) -> Path:
    job_dir = run_dir / "_job"
    job_dir.mkdir(parents=True, exist_ok=True)
    meta = doc.get("meta") or {}
    spec = {
        "run_id": run_id,
        "target": driver_target,
        "mode": mode,
        "start_url": meta.get("start_url") or "",
        "launch_target": meta.get("launch_target") or "",
        "storage_state": storage_state or "",
        "out_dir": str(run_dir),
        "variables": variables or {},
        "steps": doc.get("steps") or [],
    }
    path = job_dir / "job.json"
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def execute_ai_run(run_id: int, doc: dict, *, driver_target: str, mode: str,
                   data_dir: Path, variables: dict | None = None,
                   storage_state: str | None = None, notify,
                   node_cmd: list[str] | None = None,
                   env_extra: dict[str, str] | None = None,
                   poll_force=None) -> dict:
    from app.ui_automation import runner as py_runner
    check_force = poll_force or py_runner.is_force_finished
    run_dir = Path(data_dir) / "runs" / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    job_path = _write_job(run_id, run_dir, doc, driver_target=driver_target, mode=mode,
                          variables=variables, storage_state=storage_state)
    cmd = [*(node_cmd or ["node", "src/main.js"]), str(job_path)]
    env = dict(os.environ)
    env.update(env_extra or {})
    env.setdefault("MIDSCENE_RUN_DIR", str(run_dir / "midscene_run"))
    result: dict = {}
    killed = {"flag": False}
    with open(run_dir / "_job" / "stderr.log", "wb") as stderr_fh:
        proc = subprocess.Popen(cmd, cwd=str(settings.ui_runner_dir), env=env,
                                stdout=subprocess.PIPE, stderr=stderr_fh,
                                text=True, encoding="utf-8")

        def watchdog() -> None:
            while proc.poll() is None:
                if check_force(run_id):
                    killed["flag"] = True
                    proc.kill()
                    return
                time.sleep(_POLL_SEC)

        threading.Thread(target=watchdog, daemon=True).start()
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 依赖打印的杂音丢弃,不影响事件流
                if isinstance(event, dict) and event.get("type") == "done":
                    result = {"usage": event.get("usage"), "report_path": event.get("report_path")}
                notify(event if isinstance(event, dict) else {"type": "error", "message": "坏事件行"})
        finally:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
    if killed["flag"]:
        return {"force_finished": True}
    if not result:
        raise RuntimeError(f"Node runner 异常退出(code={proc.returncode}),详见 _job/stderr.log")
    return result
