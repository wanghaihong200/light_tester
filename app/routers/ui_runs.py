# app/routers/ui_runs.py
"""UI 自动化执行 API:创建执行(全局并发=1)、查询、SSE 预览流、失败截图文件。"""
import json
import re
import threading

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.jobs.bus import bus
from app.models import Project, UiAuthState, UiRun, UiScript
from app.schemas import UiRunOut
from app.ui_automation import dsl, runner

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


@router.post("/projects/{project_id}/ui-runs", response_model=UiRunOut, status_code=201)
def create_run(project_id: int, payload: RunCreate, db: Session = Depends(get_db)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    script = db.get(UiScript, payload.script_id)
    if script is None or script.is_deleted or script.project_id != project_id:
        raise HTTPException(400, "invalid script_id")
    errs = dsl.validate_script(script.script)
    if errs:
        raise HTTPException(400, "脚本不合法: " + ";".join(errs[:3]))
    auth_path = None
    if payload.auth_state_id is not None:
        # 登录态与脚本同源校验:存在、未软删、且属于本项目(防跨项目拖库)
        auth = db.get(UiAuthState, payload.auth_state_id)
        if auth is None or auth.is_deleted or auth.project_id != project_id:
            raise HTTPException(400, "invalid auth_state_id")
        auth_path = str(auth.storage_path)
    if not runner.RUN_SLOT.acquire(blocking=False):
        raise HTTPException(409, "已有执行在进行中,请稍后")
    # 占锁成功即拥有执行权,所有权随线程移交(线程 finally 释放),消灭「探测后让位」的竞态窗口:
    # 落库/起线程一旦失败就地释放,避免锁泄漏把后续所有请求卡死在 409
    try:
        run = UiRun(project_id=project_id, script_id=script.id, script_name=script.name,
                    mode=payload.mode, variables=payload.variables)
        db.add(run)
        db.commit()
        db.refresh(run)
        threading.Thread(target=_run_thread,
                         args=(run.id, script.script, payload.mode, payload.variables, auth_path),
                         daemon=True).start()
    except Exception:
        runner.RUN_SLOT.release()
        raise
    return run


@router.get("/projects/{project_id}/ui-runs", response_model=list[UiRunOut])
def list_runs(project_id: int, script_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(UiRun).filter(UiRun.project_id == project_id)
    if script_id is not None:
        q = q.filter(UiRun.script_id == script_id)
    return q.order_by(UiRun.id.desc()).limit(100).all()


@router.get("/ui-runs/{run_id}", response_model=UiRunOut)
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(UiRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


@router.get("/ui-runs/{run_id}/events")
async def run_events(run_id: int, db: Session = Depends(get_db)):
    """SSE 预览流:先发当前状态,running 中则持续推帧/步骤事件直到 done/error。"""
    run = db.get(UiRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
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


@router.get("/ui-runs/{run_id}/screens/{name}")
def run_screenshot(run_id: int, name: str):
    # 文件名恒为 step_<i>_<status>.jpg:非 .jpg 一律拒绝,顺带挡掉 "."/".." 目录名
    if not _NAME_RE.fullmatch(name) or name in (".", "..") or not name.endswith(".jpg"):
        raise HTTPException(400, "bad name")
    path = settings.ui_data_dir / "runs" / str(run_id) / name
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="image/jpeg")
