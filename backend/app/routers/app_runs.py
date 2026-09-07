# app/routers/app_runs.py
"""APP自动化执行 API:发起执行(单设备/分发批量同端点,每设备一行 AppRun)、SSE 状态流、强制结束。"""
import json
import threading
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.app_automation import case_schema, devices, executor, inspect_check
from app.auth import get_current_user, get_current_user_sse
from app.config import settings
from app.database import get_db
from app.jobs.bus import bus
from app.models import AppRun, AppScript, Project, User
from app.permissions import ensure_project_access
from app.schemas import AppRunOut
from app.ui_automation.runner import RUN_SLOT

router = APIRouter(prefix="/api", tags=["app-runs"])

MAX_FANOUT = 10


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


class AppRunCreate(BaseModel):
    script_id: int
    device_serials: list[str] = Field(min_length=1, max_length=MAX_FANOUT)
    perf_items: list[str] = Field(default_factory=list)
    pre_checks: list[dict] = Field(default_factory=list)
    post_checks: list[dict] = Field(default_factory=list)
    startup_time: bool = False
    allow_high_risk: bool = False


def _get_run(db: Session, run_id: int, current: User, min_role: str) -> AppRun:
    run = db.get(AppRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    ensure_project_access(db, current, run.project_id, min_role)
    return run


def _run_thread(run_id: int, case_json: dict, serial: str, opts: dict):
    """锁/槽所有权由创建端移交而来,这里只负责用完释放。"""
    try:
        executor.execute_app_run(run_id, case_json, device_serial=serial, **opts)
    finally:
        devices.lock_for(serial).release()
        RUN_SLOT.release()


@router.post("/projects/{project_id}/app-runs", response_model=list[AppRunOut], status_code=201)
def create_runs(project_id: int, payload: AppRunCreate, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    ensure_project_access(db, current, project_id, "editor")  # 发起执行 = 写
    script = db.get(AppScript, payload.script_id)
    if script is None or script.is_deleted or script.project_id != project_id:
        raise HTTPException(400, "invalid script_id")
    errs = case_schema.validate_case(script.case_json)
    if errs:
        raise HTTPException(400, "用例不合法: " + ";".join(errs[:3]))
    risky = case_schema.high_risk_actions(script.case_json)
    if risky and not payload.allow_high_risk:
        raise HTTPException(400, f"用例含高危动作({','.join(risky)}),需勾选「允许高危动作」确认")
    for name, checks in (("pre_checks", payload.pre_checks), ("post_checks", payload.post_checks)):
        check_errs = inspect_check.validate_checks(checks)
        if check_errs:
            raise HTTPException(400, f"{name} 不合法: " + ";".join(check_errs[:3]))
    serials = list(dict.fromkeys(payload.device_serials))  # 去重保序
    if len(serials) != len(payload.device_serials):
        raise HTTPException(400, "设备列表有重复")

    # 全部设备锁 all-or-nothing:任一忙 → 回滚已获取的并 409(占用即拒绝,不排队)
    acquired: list[str] = []
    for s in serials:
        if not devices.lock_for(s).acquire(blocking=False):
            for done in acquired:
                devices.lock_for(done).release()
            raise HTTPException(409, f"设备 {s} 忙,请稍后重试")
        acquired.append(s)
    # 全局执行槽:每设备占 1 个
    got_slots = 0
    try:
        for _ in serials:
            if not RUN_SLOT.acquire(blocking=False):
                raise HTTPException(409, f"执行槽已满(上限 {settings.run_slot_count}),请稍后重试")
            got_slots += 1
        batch_id = uuid.uuid4().hex if len(serials) > 1 else None
        opts = {"perf_items": payload.perf_items, "pre_checks": payload.pre_checks,
                "post_checks": payload.post_checks, "include_startup": payload.startup_time,
                "allow_high_risk": payload.allow_high_risk,
                "app_package": script.app_package}
        runs = [AppRun(project_id=project_id, script_id=script.id, script_name=script.name,
                       device_serial=s, batch_id=batch_id, pre_checks=payload.pre_checks,
                       post_checks=payload.post_checks, perf_items=payload.perf_items)
                for s in serials]
        db.add_all(runs)
        db.commit()
        for r in runs:
            db.refresh(r)
        case_json = script.case_json
        for r in runs:
            threading.Thread(target=_run_thread,
                             args=(r.id, case_json, r.device_serial, dict(opts)),
                             daemon=True).start()
        return runs
    except Exception:
        # 占锁成功即拥有执行权;落库/起线程失败就地释放,避免锁泄漏(对齐 ui_runs 注释语义)
        for _ in range(got_slots):
            RUN_SLOT.release()
        for s in serials:
            devices.lock_for(s).release()
        raise


@router.get("/projects/{project_id}/app-runs", response_model=list[AppRunOut])
def list_runs(project_id: int, script_id: int | None = None, batch_id: str | None = None,
              db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    q = db.query(AppRun).filter(AppRun.project_id == project_id, AppRun.is_deleted.is_(False))
    if script_id is not None:
        q = q.filter(AppRun.script_id == script_id)
    if batch_id is not None:
        q = q.filter(AppRun.batch_id == batch_id)
    return q.order_by(AppRun.id.desc()).limit(100).all()


@router.get("/app-runs/{run_id}", response_model=AppRunOut)
def get_run(run_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return _get_run(db, run_id, current, "viewer")


@router.get("/app-runs/{run_id}/events")
async def run_events(run_id: int, db: Session = Depends(get_db),
                     current: User = Depends(get_current_user_sse)):
    """SSE 状态流:先发当前状态;终态补 snapshot 后断流,否则等 done/error(步骤级事件不承诺)。"""
    run = db.get(AppRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    ensure_project_access(db, current, run.project_id, "editor")  # 实时流=写会话语义
    key = f"app-{run_id}"
    queue = bus.subscribe(key)
    snapshot = {"status": run.status, "run_state": run.run_state, "error": run.error}

    async def stream():
        try:
            yield _sse({"type": "status", "status": snapshot["status"]})
            if snapshot["status"] in executor.TERMINAL:
                yield _sse({"type": "snapshot", **snapshot})
                return
            while True:
                event = await queue.get()
                yield _sse(event)
                if event.get("type") in ("done", "error"):
                    return
        finally:
            bus.unsubscribe(key, queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/app-runs/{run_id}/force-finish", response_model=AppRunOut)
def force_finish(run_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """强制结束执行中的 run:状态置 cancelled(协作式——执行线程在阶段边界检测标志后退出,
    阻塞中的 CLI 回放需等当前 run 自然结束后不再写库;_persist 终态防覆盖保证状态不被翻回)。"""
    run = _get_run(db, run_id, current, "editor")
    if run.status in executor.TERMINAL:
        raise HTTPException(400, "该执行已结束,无需强制结束")
    run.status = "cancelled"
    run.error = "用户强制结束"
    run.started_at = run.started_at or datetime.now()
    run.finished_at = datetime.now()
    db.commit()
    executor.mark_force_finished(run_id)
    executor.notify(run_id, {"type": "done", "status": "cancelled"})
    db.refresh(run)
    return run
