"""持续集成执行域 API:执行计划 / 接口用例注册表 / 执行记录 / Jenkins 连接(ADR-0012)。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import git_service
from app.auth import get_current_user
from app.cicd import api_scan, registry
from app.cicd.jenkins_job import job_name  # noqa: F401(后续任务用)
from app.database import get_db
from app.models import AutomationRepo, ExecutionPlan, Project, User
from app.permissions import ensure_project_access
from app.schemas import ExecutionPlanOut, InterfaceCaseOut
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
