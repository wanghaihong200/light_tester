"""持续集成执行域 API:执行计划 / 接口用例注册表 / 执行记录 / Jenkins 连接(ADR-0012)。"""
import json as _json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import git_service
from app.auth import get_current_user, get_current_user_sse
from app.cicd import api_scan, executor, freshness, jenkins_client, registry
from app.cicd.jenkins_job import job_name  # noqa: F401(后续任务用)
from app.config import settings
from app.database import get_db
from app.jobs.bus import bus
from app.models import (AutomationRepo, CiRun, ExecutionPlan, JenkinsConnection,
                        Project, User)
from app.permissions import ensure_project_access
from app.schemas import CiRunOut, ExecutionPlanOut, InterfaceCaseOut
from app.ui_automation.playwright_export import slugify

router = APIRouter(prefix="/api", tags=["cicd"])


class ScanIn(BaseModel):
    branch: str = Field(min_length=1, max_length=200)


def _api_repo(db: Session, project_id: int) -> AutomationRepo:
    repo = db.query(AutomationRepo).filter_by(project_id=project_id, kind="api",
                                              is_deleted=False).first()
    if repo is None:
        raise HTTPException(400, "项目未配置 api 自动化仓,请先在「自动化工程」配置")
    return repo


@router.post("/projects/{project_id}/interface-cases/scan")
def scan_interface_cases(project_id: int, payload: ScanIn, db: Session = Depends(get_db),
                         current: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    ensure_project_access(db, current, project_id, "editor")
    repo = _api_repo(db, project_id)
    try:
        sync = git_service.sync_repo(repo, payload.branch)
    except git_service.GitError as e:
        raise HTTPException(400, f"分支同步失败: {e}") from e
    from pathlib import Path

    scanned = api_scan.scan_workspace(git_service.working_copy_path(repo))
    return registry.sync_registry(db, project_id, payload.branch, scanned,
                                  commit=sync.commit_short)


@router.get("/projects/{project_id}/interface-cases", response_model=list[InterfaceCaseOut])
def list_interface_cases(project_id: int, branch: str, db: Session = Depends(get_db),
                         current: User = Depends(get_current_user)):
    from app.models import InterfaceCase

    ensure_project_access(db, current, project_id, "viewer")
    q = db.query(InterfaceCase).filter_by(project_id=project_id, branch=branch, is_deleted=False)
    return q.order_by(InterfaceCase.class_name, InterfaceCase.method).limit(2000).all()


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    kind: str = Field(pattern="^(ui|api)$")
    branch: str = Field(min_length=1, max_length=200)
    selection: list[dict] = Field(default_factory=list)


class PlanUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    branch: str | None = Field(default=None, min_length=1, max_length=200)
    selection: list[dict] | None = None


def _enrich_selection(kind: str, items: list[dict]) -> list[dict]:
    """ui 项补 file(与 playwright_export 导出文件名规则严格一致);api 项补 ref。"""
    out: list[dict] = []
    for it in items:
        if kind == "ui":
            sid, name = it.get("script_id"), (it.get("name") or "").strip()
            if not isinstance(sid, int) or isinstance(sid, bool) or not name:
                raise HTTPException(400, "ui 选择项需要 int script_id 与非空 name")
            out.append({"script_id": sid, "name": name,
                        "file": f"test_{slugify(sid, name)}.py"})
        else:
            cls, method = (it.get("class_name") or "").strip(), (it.get("method") or "").strip()
            if not cls or not method:
                raise HTTPException(400, "api 选择项需要非空 class_name 与 method")
            out.append({"ref": f"{cls}#{method}", "class_name": cls, "method": method})
    return out


def _get_plan(db: Session, plan_id: int, project_id: int) -> ExecutionPlan:
    plan = db.get(ExecutionPlan, plan_id)
    if plan is None or plan.is_deleted or plan.project_id != project_id:
        raise HTTPException(404, "plan not found")
    return plan


@router.get("/projects/{project_id}/ci-plans", response_model=list[ExecutionPlanOut])
def list_plans(project_id: int, db: Session = Depends(get_db),
               current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    return db.query(ExecutionPlan).filter_by(project_id=project_id, is_deleted=False) \
        .order_by(ExecutionPlan.id.desc()).all()


@router.post("/projects/{project_id}/ci-plans", response_model=ExecutionPlanOut, status_code=201)
def create_plan(project_id: int, payload: PlanIn, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(404, "project not found")
    ensure_project_access(db, current, project_id, "editor")
    plan = ExecutionPlan(project_id=project_id, name=payload.name,
                         description=payload.description, kind=payload.kind,
                         branch=payload.branch,
                         selection=_enrich_selection(payload.kind, payload.selection),
                         created_by=current.id, updated_by=current.id)
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@router.put("/ci-plans/{plan_id}", response_model=ExecutionPlanOut)
def update_plan(plan_id: int, payload: PlanUpdate, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    plan = db.get(ExecutionPlan, plan_id)
    if plan is None or plan.is_deleted:
        raise HTTPException(404, "plan not found")
    ensure_project_access(db, current, plan.project_id, "editor")
    if payload.name is not None:
        plan.name = payload.name
    if payload.description is not None:
        plan.description = payload.description
    if payload.branch is not None:
        plan.branch = payload.branch
    if payload.selection is not None:
        plan.selection = _enrich_selection(plan.kind, payload.selection)
    plan.updated_by = current.id
    db.commit()
    db.refresh(plan)
    return plan


@router.delete("/ci-plans/{plan_id}", status_code=204)
def delete_plan(plan_id: int, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    plan = db.get(ExecutionPlan, plan_id)
    if plan is None or plan.is_deleted:
        raise HTTPException(404, "plan not found")
    ensure_project_access(db, current, plan.project_id, "editor")
    plan.is_deleted = True
    plan.updated_by = current.id
    db.commit()


def _detail_str(e: HTTPException) -> str:
    """HTTPException.detail 转批量失败行文案(dict detail 转 JSON 文本)。"""
    import json

    if isinstance(e.detail, str):
        return e.detail
    return json.dumps(e.detail, ensure_ascii=False)


class PreflightIn(BaseModel):
    plan_ids: list[int] = Field(min_length=1)


class TriggerIn(BaseModel):
    plan_ids: list[int] = Field(min_length=1)
    confirm_stale: bool = False


@router.post("/projects/{project_id}/ci-runs/preflight")
def preflight(project_id: int, payload: PreflightIn, db: Session = Depends(get_db),
              current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "editor")
    out = []
    for pid in payload.plan_ids:
        plan = db.get(ExecutionPlan, pid)
        if plan is None or plan.is_deleted or plan.project_id != project_id:
            raise HTTPException(400, f"计划 {pid} 不存在")
        item = {"plan_id": plan.id, "name": plan.name, "kind": plan.kind,
                "branch": plan.branch, "freshness": None, "valid": 0, "missing": 0,
                "error": None}
        try:
            repo = executor.repo_for(db, project_id, plan.kind)
            git_service.sync_repo(repo, plan.branch)
            item["freshness"] = freshness.check_freshness(repo, plan.branch)
            snap, _ = executor._resolve_selection(db, plan, git_service.working_copy_path(repo))
            item["valid"] = sum(1 for s in snap if not s.get("skipped"))
            item["missing"] = len(snap) - item["valid"]
        except git_service.GitError as e:
            item["error"] = f"分支/仓不可用: {e}"
        except HTTPException as e:
            item["error"] = _detail_str(e)
        out.append(item)
    return out


@router.post("/projects/{project_id}/ci-runs")
def trigger_runs(project_id: int, payload: TriggerIn, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "editor")
    runs: list[CiRun] = []
    failures: list[dict] = []
    for pid in payload.plan_ids:
        plan = db.get(ExecutionPlan, pid)
        if plan is None or plan.is_deleted or plan.project_id != project_id:
            failures.append({"plan_id": pid, "error": "计划不存在"})
            continue
        try:
            runs.append(executor.trigger_plan(db, current, plan,
                                              confirm_stale=payload.confirm_stale))
        except HTTPException as e:
            if e.status_code == 409:  # 确认新鲜度门:原样上抛(dict detail 由前端弹确认)
                raise
            failures.append({"plan_id": pid, "error": _detail_str(e)})
    return {"runs": [CiRunOut.model_validate(r) for r in runs],
            "failures": failures}


@router.get("/projects/{project_id}/ci-runs", response_model=list[CiRunOut])
def list_runs(project_id: int, db: Session = Depends(get_db),
              current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    return db.query(CiRun).filter_by(project_id=project_id) \
        .order_by(CiRun.id.desc()).limit(100).all()


def _get_run(db: Session, run_id: int, current: User) -> CiRun:
    run = db.get(CiRun, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    ensure_project_access(db, current, run.project_id, "viewer")
    return run


@router.get("/ci-runs/{run_id}", response_model=CiRunOut)
def get_run(run_id: int, db: Session = Depends(get_db),
            current: User = Depends(get_current_user)):
    return _get_run(db, run_id, current)


def _sse(event: dict) -> str:
    return f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/ci-runs/{run_id}/events")
async def run_events(run_id: int, db: Session = Depends(get_db),
                     current: User = Depends(get_current_user_sse)):
    """SSE 直播:先 status 快照 + 日志尾部回放(≤8KB),再持续推增量到 done/error 断流。"""
    run = _get_run(db, run_id, current)
    key = f"ci_{run.id}"
    queue = bus.subscribe(key)
    snapshot = {"status": run.status, "total": run.total, "passed": run.passed,
                "failed": run.failed, "skipped": run.skipped, "results": run.results,
                "error": run.error}

    async def stream():
        try:
            yield _sse({"type": "status", "status": run.status})
            if run.status in ("success", "failure", "aborted", "error"):
                yield _sse({"type": "snapshot", **snapshot})
                return
            log_path = settings.ci_data_dir / "runs" / str(run.id) / "console.log"
            if log_path.exists():
                tail = log_path.read_bytes()[-8192:]
                if tail:
                    yield _sse({"type": "log", "text": tail.decode("utf-8", "replace")})
            while True:
                event = await queue.get()
                yield _sse(event)
                if event.get("type") in ("done", "error"):
                    return
        finally:
            bus.unsubscribe(key, queue)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/ci-runs/{run_id}/stop", response_model=CiRunOut)
def stop_run(run_id: int, db: Session = Depends(get_db),
             current: User = Depends(get_current_user)):
    run = _get_run(db, run_id, current)
    ensure_project_access(db, current, run.project_id, "editor")
    if run.status not in ("queued", "running"):
        raise HTTPException(400, "该执行已结束,无需停止")
    conn = db.query(JenkinsConnection).first()
    if conn is None:
        raise HTTPException(400, "Jenkins 连接未配置")
    if run.build_number is not None:
        try:
            with executor.client_from(conn) as client:
                client.stop_build(run.jenkins_job, run.build_number)
        except jenkins_client.JenkinsError as e:
            raise HTTPException(502, f"Jenkins 停止失败: {e}") from e
    run.status = "aborted"
    run.finished_at = datetime.now()
    if run.started_at is None:
        run.started_at = run.finished_at
    db.commit()
    bus.publish_nowait(f"ci_{run.id}", {"type": "done", "status": "aborted"})
    return run


@router.post("/ci-runs/{run_id}/rerun", response_model=CiRunOut, status_code=201)
def rerun_run(run_id: int, db: Session = Depends(get_db),
              current: User = Depends(get_current_user)):
    run = _get_run(db, run_id, current)
    ensure_project_access(db, current, run.project_id, "editor")
    plan = db.get(ExecutionPlan, run.plan_id)
    if plan is None or plan.is_deleted:
        raise HTTPException(400, "原计划已删除,无法重跑")
    return executor.trigger_plan(db, current, plan, confirm_stale=True)


class JenkinsConnectionIn(BaseModel):
    base_url: str = Field(min_length=1, max_length=500, pattern=r"^https?://")
    api_user: str = Field(min_length=1, max_length=200)
    api_token: str = Field(min_length=1, max_length=500)
    gitlab_exposed_base: str = Field(default="http://host.docker.internal:8090", max_length=500)
    credential_id: str = Field(default="gitlab-creds", max_length=200)


def _conn_out(conn: JenkinsConnection | None) -> dict:
    if conn is None:
        return {"configured": False, "base_url": "", "api_user": "", "api_token": "",
                "gitlab_exposed_base": "http://host.docker.internal:8090",
                "credential_id": "gitlab-creds"}
    return {"configured": True, "base_url": conn.base_url, "api_user": conn.api_user,
            "api_token": conn.api_token, "gitlab_exposed_base": conn.gitlab_exposed_base,
            "credential_id": conn.credential_id}


def _require_admin(current: User) -> None:
    if not current.is_admin:
        raise HTTPException(403, "仅管理员可配置 Jenkins 连接")


@router.get("/jenkins/connection")
def get_jenkins_connection(db: Session = Depends(get_db),
                           current: User = Depends(get_current_user)):
    _require_admin(current)
    return _conn_out(db.query(JenkinsConnection).first())


@router.put("/jenkins/connection")
def put_jenkins_connection(payload: JenkinsConnectionIn, db: Session = Depends(get_db),
                           current: User = Depends(get_current_user)):
    _require_admin(current)
    conn = db.query(JenkinsConnection).first()
    if conn is None:
        conn = JenkinsConnection(id=1)
        db.add(conn)
    conn.base_url = payload.base_url.rstrip("/")
    conn.api_user = payload.api_user
    conn.api_token = payload.api_token
    conn.gitlab_exposed_base = payload.gitlab_exposed_base
    conn.credential_id = payload.credential_id
    conn.updated_by = current.id
    db.commit()
    return _conn_out(conn)


@router.post("/jenkins/connection/test")
def test_jenkins_connection(db: Session = Depends(get_db),
                            current: User = Depends(get_current_user)):
    _require_admin(current)
    conn = db.query(JenkinsConnection).first()
    if conn is None:
        raise HTTPException(400, "尚未配置 Jenkins 连接")
    try:
        with executor.client_from(conn) as client:
            return client.test_connection()
    except jenkins_client.JenkinsError as e:
        raise HTTPException(400, str(e)) from e
