"""APP 自动化执行引擎:每台设备一个 daemon 线程,顺序执行
pre_checks → case_import → perf_start → run(阻塞到终态) → perf_stop/analyze → startup_time → post_checks → 终态落库。
设计对齐 ui_automation/runner.py:终态防覆盖(_persist)、环境级失败兜底、协作式强制结束。
SSE 只推 status/done/error(步骤级实时流不承诺,ADR-0008)。"""
import json
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from app.app_automation import case_schema, inspect_check, solopi_cli
from app.config import settings
from app.database import SessionLocal
from app.models import AppRun
from app.solopi_perf import register_run_perf_record

TERMINAL = ("passed", "failed", "cancelled")
_FORCE_FINISHED: set[int] = set()
_FORCE_GUARD = threading.Lock()


def mark_force_finished(run_id: int) -> None:
    with _FORCE_GUARD:
        _FORCE_FINISHED.add(run_id)


def _is_force_finished(run_id: int) -> bool:
    with _FORCE_GUARD:
        return run_id in _FORCE_FINISHED


def notify(run_id: int, event: dict) -> None:
    """线程内回调 → 主循环 bus。key 用 f"app-{run_id}" 命名空间,防与 ui_runs 的裸 int key 撞订阅。"""
    import asyncio

    from app.jobs.bus import bus
    from app.ui_automation.loopref import ui_loop
    loop = ui_loop()
    if loop is not None and not loop.is_closed():
        # 已关闭的 loop 不投递(SSE 消费侧容忍丢事件):否则 run_coroutine_threadsafe 抛
        # RuntimeError,会被 execute_app_run 的 except 误判为环境失败。
        asyncio.run_coroutine_threadsafe(bus.publish(f"app-{run_id}", event), loop)


def _persist(run_id: int, **fields) -> None:
    """终态防覆盖:已终态的 run 不再被线程迟到写入覆盖(对齐 runner._persist)。"""
    with SessionLocal() as db:
        run = db.get(AppRun, run_id)
        if run is None or run.status in TERMINAL:
            return
        for k, v in fields.items():
            setattr(run, k, v)
        db.commit()


def _persist_env_failure(run_id: int, err: str) -> None:
    _persist(run_id, status="failed", error=err[:500], finished_at=datetime.now())


def _extract_run(payload: dict) -> dict:
    """run/result 返回里定位 run 对象:嵌套 "run" 或顶层,防御 CLI 版本差异(单点改动处)。"""
    if isinstance(payload, dict):
        if isinstance(payload.get("run"), dict):
            return payload["run"]
        if "state" in payload:
            return payload
    return {}


def _run_checkpoint(serial: str, checks: list[dict]) -> tuple[list[dict], bool]:
    payload = solopi_cli.inspect(serial)
    results = inspect_check.evaluate_checks((payload or {}).get("page") or {}, checks)
    return results, all(r["passed"] for r in results)


def execute_app_run(run_id: int, case_json: dict, *, device_serial: str, perf_items: list[str],
                    pre_checks: list[dict], post_checks: list[dict], include_startup: bool,
                    allow_high_risk: bool, app_package: str) -> None:
    run_dir = Path(settings.app_data_dir) / "runs" / str(run_id)
    confirm = bool(allow_high_risk and case_schema.high_risk_actions(case_json))
    perf_session: str | None = None
    check_results: dict = {"pre": None, "post": None}
    post_ok = True
    post_rows: list[dict] = []
    try:
        _persist(run_id, status="running", started_at=datetime.now())
        notify(run_id, {"type": "status", "status": "running"})

        if pre_checks:
            pre_rows, pre_ok = _run_checkpoint(device_serial, pre_checks)
            check_results["pre"] = pre_rows
            if not pre_ok:
                _persist(run_id, status="failed", check_results=check_results, finished_at=datetime.now(),
                         error="前置检查点未通过: " + ";".join(r["detail"] for r in pre_rows if not r["passed"]))
                notify(run_id, {"type": "done", "status": "failed"})
                return

        run_dir.mkdir(parents=True, exist_ok=True)
        case_file = run_dir / "case.json"
        case_file.write_text(json.dumps(case_json, ensure_ascii=False), encoding="utf-8")
        # --replace 整覆盖:同设备已有同名用例时端上回 duplicate_case(rc=2),同一脚本将永远无法
        # 第二次执行(HarnessSchemeResolver.java:411)。平台 case_json 是唯一事实源,执行前整覆盖
        # 是正确幂等;同设备并发已被 per-serial 锁串行化(终审 C2)。
        solopi_cli.case_import(str(case_file), device_serial, replace=True, confirm_high_risk=confirm)

        if perf_items:
            started = solopi_cli.perf_start(device_serial, perf_items, target_package=app_package or None)
            # sessionId 字段名防御性提取(CLI 版本差异单点改动处)
            perf_session = str((started or {}).get("sessionId") or (started or {}).get("session_id")
                               or (started or {}).get("id") or "")

        payload = solopi_cli.run_case(case_json["caseName"], device_serial,
                                      str(run_dir / "artifacts"),
                                      target_package=app_package or None, run_timeout=600,
                                      confirm_high_risk=confirm)

        if perf_session:
            try:
                solopi_cli.perf_stop(device_serial, perf_session, str(run_dir / "perf"))
                _persist(run_id, perf_summary=solopi_cli.perf_analyze(str(run_dir / "perf")))
            except solopi_cli.CliError as e:
                _persist(run_id, perf_summary={"error": f"perf 采集收尾失败: {e.message}"})

        if include_startup and app_package:
            try:
                _persist(run_id, startup_summary=solopi_cli.startup_time(device_serial, app_package))
            except solopi_cli.CliError as e:
                _persist(run_id, startup_summary={"error": f"启动耗时采集失败: {e.message}"})

        if _is_force_finished(run_id):
            # 强制结束已由 force-finish 端点落库;这里兜底防竞态(端点未来得及写时补终态)
            _persist(run_id, status="cancelled", error="用户强制结束", finished_at=datetime.now())
            notify(run_id, {"type": "done", "status": "cancelled"})
            return

        if post_checks:
            post_rows, post_ok = _run_checkpoint(device_serial, post_checks)
            check_results["post"] = post_rows

        run_obj = _extract_run(payload)
        state = run_obj.get("state") or "failed"
        err = run_obj.get("error") or ""
        status = {"passed": "passed", "cancelled": "cancelled"}.get(state, "failed")
        if status == "passed" and not post_ok:
            status = "failed"
            err = "后置检查点未通过: " + ";".join(r["detail"] for r in post_rows if not r["passed"])
        _persist(run_id, status=status, run_state=state, results=run_obj.get("results"),
                 check_results=check_results if any(check_results.values()) else None,
                 error=err or None, finished_at=datetime.now())
        notify(run_id, {"type": "done", "status": status, "state": state})
        register_run_perf_record(run_id)  # 终态且有效 perf CSV → 登记性能引用行(ADR-0010)
    except (solopi_cli.CliError, RuntimeError, OSError, subprocess.SubprocessError) as e:
        msg = getattr(e, "message", None) or str(e)
        _persist_env_failure(run_id, msg)
        notify(run_id, {"type": "error", "message": msg[:500]})
    register_run_perf_record(run_id)  # env 失败若已有部分 perf 数据,同样登记(崩溃前曲线有分析价值)
