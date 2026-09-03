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
from app.models import Project, UiRun, UiScript
from app.schemas import UiRunOut
from app.ui_automation import dsl, runner

router = APIRouter(prefix="/api", tags=["ui-runs"])

# 截图文件名白名单:仅字母数字下划线点横线,防路径穿越
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


class RunCreate(BaseModel):
    script_id: int
    mode: str = Field(default="headless", pattern="^(headless|headed)$")
    variables: dict = Field(default_factory=dict)


def _run_thread(run_id: int, doc: dict, mode: str, variables: dict, auth_path: str | None):
    if not runner.RUN_SLOT.acquire(blocking=False):
        return  # 理论不可达:创建端已 409
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
    if not runner.RUN_SLOT.acquire(blocking=False):
        raise HTTPException(409, "已有执行在进行中,请稍后")
    runner.RUN_SLOT.release()  # 占用在 _run_thread 里真正发生,先探测后让位避免锁泄漏
    run = UiRun(project_id=project_id, script_id=script.id, script_name=script.name,
                mode=payload.mode, variables=payload.variables)
    db.add(run)
    db.commit()
    db.refresh(run)
    threading.Thread(target=_run_thread,
                     args=(run.id, script.script, payload.mode, payload.variables, None),
                     daemon=True).start()
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
    if not _NAME_RE.fullmatch(name):
        raise HTTPException(400, "bad name")
    path = settings.ui_data_dir / "runs" / str(run_id) / name
    if not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path, media_type="image/jpeg")
