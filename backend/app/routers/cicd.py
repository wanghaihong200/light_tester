"""持续集成执行域 API:执行计划 / 接口用例注册表 / 执行记录 / Jenkins 连接(ADR-0012)。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import git_service
from app.auth import get_current_user
from app.cicd import api_scan, registry
from app.database import get_db
from app.models import AutomationRepo, Project, User
from app.permissions import ensure_project_access
from app.schemas import InterfaceCaseOut

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
