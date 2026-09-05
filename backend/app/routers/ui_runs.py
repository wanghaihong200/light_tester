# app/routers/ui_runs.py
"""UI 自动化执行 API:创建执行(全局并发=1)、查询、SSE 预览流、失败截图文件。"""
import json
import re
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, get_current_user_sse
from app.config import settings
from app.database import get_db
from app.jobs.bus import bus
from app.models import Project, UiAuthState, UiRun, UiScript, User
from app.permissions import ensure_project_access
from app.schemas import UiRunOut
from app.ui_automation import adb, compose, dsl, node_runner, nodepath, runner, vision

router = APIRouter(prefix="/api", tags=["ui-runs"])

# 截图文件名白名单:仅字母数字下划线点横线,防路径穿越;再挡 "."/".."(避免 FileResponse 读目录 500)
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


class RunCreate(BaseModel):
    script_id: int
    mode: str = Field(default="headless", pattern="^(headless|headed)$")
    variables: dict = Field(default_factory=dict)
    auth_state_id: int | None = None  # 带登录态启动 context,脚本不必录登录步骤


def _run_thread(run_id: int, doc: dict, mode: str, variables: dict, auth_path: str | None):
    """执行线程:锁的所有权由创建端移交而来,这里只负责用完释放。"""
    try:
        runner.execute_script(run_id, doc, mode=mode, variables=variables,
                              auth_state_path=auth_path,
                              data_dir=settings.ui_data_dir,
                              notify=lambda e: runner._notify_bus(run_id, e))
    finally:
        runner.RUN_SLOT.release()


def _resolver(db: Session, project_id: int):
    """run_sub 片段解析器:同项目、未软删的脚本才可被引用。"""
    def resolve(script_id) -> dict | None:
        if not isinstance(script_id, int) or isinstance(script_id, bool):
            return None
        sub = db.get(UiScript, script_id)
        if sub is None or sub.is_deleted or sub.project_id != project_id:
            return None
        return sub.script
    return resolve


def _ai_run_thread(run_id: int, doc: dict, target: str, mode: str, variables: dict,
                   auth: UiAuthState | None):
    """Node 路径执行线程:快照恢复→预渲染→spawn Node;done 事件负责落库(含 ai_usage)。"""
    results: list[dict] = []

    def on_event(e: dict) -> None:
        runner._notify_bus(run_id, e)
        t = e.get("type")
        if t == "step_end":
            results.append({"index": e.get("index"), "step_id": e.get("step_id"),
                            "action": e.get("action", ""), "status": e.get("status", "failed"),
                            "error": e.get("error"), "screenshot": e.get("screenshot"),
                            "elapsed_ms": e.get("elapsed_ms", 0)})
        elif t == "done":
            summary = e.get("summary") or {}
            usage = dict(e.get("usage") or {})
            if e.get("report_path"):
                usage["report_path"] = e["report_path"]
            runner._persist(run_id, status="completed" if e.get("status") == "completed" else "failed",
                            results=results, total=summary.get("total", len(results)),
                            passed=summary.get("passed", 0), failed=summary.get("failed", 0),
                            error=None, ai_usage=usage or None)

    try:
        storage_state = None
        if auth is not None:
            if auth.kind == "android_snapshot":
                # 快照恢复先于一切步骤,失败即环境级失败(登录态在步骤执行前生效)
                adb.restore_app_data(auth.app_package, Path(auth.storage_path))
            else:
                storage_state = str(auth.storage_path)  # web_storage:交给 PlaywrightAgent 的 context
        node_runner.execute_ai_run(run_id, doc, driver_target=target, mode=mode,
                                   variables=variables, storage_state=storage_state,
                                   data_dir=settings.ui_data_dir,
                                   notify=on_event, env_extra=vision.vision_env())
    except Exception as e:
        # 宽捕:Node 崩溃(RuntimeError)/快照恢复失败(TimeoutExpired/FileNotFoundError)等
        # 一切异常都转环境级失败,状态不能停在 running
        err = str(e)[:500]
        runner._persist_env_failure(run_id, err)
        runner._notify_bus(run_id, {"type": "error", "message": err})
    finally:
        nodepath.TARGET_LOCKS[target].release()
        runner.RUN_SLOT.release()


@router.post("/projects/{project_id}/ui-runs", response_model=UiRunOut, status_code=201)
def create_run(project_id: int, payload: RunCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    ensure_project_access(db, current, project_id, "editor")  # 发起执行 = 写(共识硬点)
    script = db.get(UiScript, payload.script_id)
    if script is None or script.is_deleted or script.project_id != project_id:
        raise HTTPException(400, "invalid script_id")
    errs = dsl.validate_script(script.script)
    if errs:
        raise HTTPException(400, "脚本不合法: " + ";".join(errs[:3]))
    # run_sub 先展开再分流:展开后的 steps 才参与「是否走 Node」的判定
    steps, expand_errs = compose.expand_steps(script.script.get("steps") or [],
                                              _resolver(db, project_id))
    if expand_errs:
        raise HTTPException(400, "脚本不合法: " + ";".join(expand_errs[:3]))
    expanded = {**script.script, "steps": steps}
    target = nodepath.driver_target(expanded)
    use_node = nodepath.needs_node(expanded)
    auth_row = None
    auth_path = None
    if payload.auth_state_id is not None:
        # 登录态与脚本同源校验:存在、未软删、且属于本项目(防跨项目拖库)
        auth_row = db.get(UiAuthState, payload.auth_state_id)
        if auth_row is None or auth_row.is_deleted or auth_row.project_id != project_id:
            raise HTTPException(400, "invalid auth_state_id")
        if auth_row.kind == "android_snapshot":
            if not use_node or target != "android":
                raise HTTPException(400, "应用数据快照仅用于 Android 端脚本执行")
        auth_path = None if auth_row.kind == "android_snapshot" else str(auth_row.storage_path)
    if use_node:
        # 端锁先于执行槽:同端同时至多一个 Node 会话,占用直接 409(不排队)
        if not nodepath.TARGET_LOCKS[target].acquire(blocking=False):
            raise HTTPException(409, f"「{target}」端设备忙,请稍后重试")
    if not runner.RUN_SLOT.acquire(blocking=False):
        if use_node:
            nodepath.TARGET_LOCKS[target].release()
        raise HTTPException(409, f"执行槽已满(上限 {settings.run_slot_count}),请稍后重试")
    # 占锁成功即拥有执行权,所有权随线程移交(线程 finally 释放),消灭「探测后让位」的竞态窗口:
    # 落库/起线程一旦失败就地释放,避免锁泄漏把后续所有请求卡死在 409
    try:
        run = UiRun(project_id=project_id, script_id=script.id, script_name=script.name,
                    mode=payload.mode, variables=payload.variables, driver_target=target)
        db.add(run)
        db.commit()
        db.refresh(run)
        if use_node:
            threading.Thread(target=_ai_run_thread,
                             args=(run.id, expanded, target, payload.mode, payload.variables, auth_row),
                             daemon=True).start()
        else:
            threading.Thread(target=_run_thread,
                             args=(run.id, expanded, payload.mode, payload.variables, auth_path),
                             daemon=True).start()
    except Exception:
        if use_node:
            nodepath.TARGET_LOCKS[target].release()
        runner.RUN_SLOT.release()
        raise
    return run


@router.get("/projects/{project_id}/ui-runs", response_model=list[UiRunOut])
def list_runs(project_id: int, script_id: int | None = None, driver_target: str | None = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # driver_target 可选筛选:按执行端(web/android/harmony)过滤历史
    ensure_project_access(db, current, project_id, "viewer")
    q = db.query(UiRun).filter(UiRun.project_id == project_id)
    if script_id is not None:
        q = q.filter(UiRun.script_id == script_id)
    if driver_target is not None:
        q = q.filter(UiRun.driver_target == driver_target)
    return q.order_by(UiRun.id.desc()).limit(100).all()


@router.get("/ui-runs/{run_id}", response_model=UiRunOut)
def get_run(run_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    run = db.get(UiRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    ensure_project_access(db, current, run.project_id, "viewer")
    return run


@router.get("/ui-runs/{run_id}/events")
async def run_events(run_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user_sse)):
    """SSE 预览流:先发当前状态,running 中则持续推帧/步骤事件直到 done/error。"""
    run = db.get(UiRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    # 闸门在订阅前:无权限者连半开流都拿不到,也不留需清理的订阅
    ensure_project_access(db, current, run.project_id, "editor")
    queue = bus.subscribe(run_id)
    # ORM 陷阱:Depends 的 db 在生成器执行时可能已关闭,先取值存局部变量
    snapshot = {"status": run.status, "step_results": run.step_results, "error": run.error,
                "steps_total": run.steps_total, "steps_passed": run.steps_passed,
                "steps_failed": run.steps_failed}

    async def stream():
        try:
            yield _sse({"type": "status", "status": snapshot["status"]})
            if snapshot["status"] in ("completed", "failed"):
                yield _sse({"type": "snapshot", **snapshot})
                return
            while True:
                event = await queue.get()
                yield _sse(event)
                if event.get("type") in ("done", "error"):
                    return
        finally:
            bus.unsubscribe(run_id, queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/ui-runs/{run_id}/force-finish", response_model=UiRunOut)
def force_finish(run_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """强制结束执行中/排队的 run,状态置「执行异常」(2026-09-04 需求:异常挂起时可手动收口)。
    执行线程活着 → 取消标志让其在下一个步骤边界退出并释放 RUN_SLOT(协作式,长步骤需跑完当前步);
    线程已死(后端重启等)→ 纯状态修复。线程迟到的落库被 _persist 终态防覆盖挡住。"""
    run = db.get(UiRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    ensure_project_access(db, current, run.project_id, "editor")  # 强制结束 = 写
    if run.status in ("completed", "failed"):
        raise HTTPException(400, "该执行已结束,无需强制结束")
    run.status = "failed"
    run.error = "执行异常: 用户强制结束"
    run.started_at = run.started_at or datetime.now()
    run.finished_at = datetime.now()
    db.commit()
    runner.mark_force_finished(run_id)
    # 推终态给 SSE 订阅者:前端按 done 收尾断流(迟到的事件被前端 finished 守卫忽略)
    runner._notify_bus(run_id, {"type": "done", "status": "failed",
                                "summary": {"total": run.steps_total, "passed": run.steps_passed,
                                            "failed": run.steps_failed, "duration_ms": 0}})
    return run


@router.get("/ui-runs/{run_id}/screens/{name}")
def run_screenshot(run_id: int, name: str, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # 文件名恒为 step_<i>_<status>.jpg:非 .jpg 一律拒绝,顺带挡掉 "."/".." 目录名
    if not _NAME_RE.fullmatch(name) or name in (".", "..") or not name.endswith(".jpg"):
        raise HTTPException(400, "bad name")
    run = db.get(UiRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    ensure_project_access(db, current, run.project_id, "viewer")  # 截图读 = viewer
    path = settings.ui_data_dir / "runs" / str(run_id) / name
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="image/jpeg")
