"""APP自动化脚本 API(独立域,不碰 ui_scripts)。用例体 = SoloPi 原生 JSON 唯一事实源,原样存储。"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.app_automation.case_schema import high_risk_actions, validate_case
from app.auth import get_current_user
from app.database import get_db
from app.models import AppScript, Project, User
from app.permissions import ensure_project_access
from app.schemas import AppScriptOut

router = APIRouter(prefix="/api", tags=["app-scripts"], dependencies=[Depends(get_current_user)])


def _get_project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    return p


def _get_script(db: Session, current: User, script_id: int, min_role: str) -> AppScript:
    """Task 8/12 复用的取行闸:404=不存在或已软删(不泄漏存在性),403=成员但角色不足。"""
    s = db.get(AppScript, script_id)
    if s is None or s.is_deleted:
        raise HTTPException(404, "script not found")
    ensure_project_access(db, current, s.project_id, min_role)
    return s


def _check_case(case: dict, allow_high_risk: bool) -> None:
    errs = validate_case(case)
    if errs:
        raise HTTPException(400, "用例不合法: " + ";".join(errs[:3]))
    risky = high_risk_actions(case)
    if risky and not allow_high_risk:
        raise HTTPException(400, f"用例含高危动作({','.join(risky)}),需勾选「允许高危动作」确认")


class AppScriptSave(BaseModel):
    name: str | None = None
    description: str | None = None
    case: dict
    allow_high_risk: bool = False


class AppScriptPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    case: dict | None = None
    allow_high_risk: bool = False


@router.post("/projects/{project_id}/app-scripts", response_model=AppScriptOut, status_code=201)
def create_script(project_id: int, payload: AppScriptSave, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    _get_project(db, project_id)
    ensure_project_access(db, current, project_id, "editor")
    _check_case(payload.case, payload.allow_high_risk)
    s = AppScript(project_id=project_id,
                  name=payload.name or str(payload.case.get("caseName") or "") or "未命名用例",
                  description=payload.description, case_json=payload.case,
                  app_package=str(payload.case.get("targetAppPackage") or ""),
                  created_by=current.id, updated_by=current.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/projects/{project_id}/app-scripts", response_model=list[AppScriptOut])
def list_scripts(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _get_project(db, project_id)
    ensure_project_access(db, current, project_id, "viewer")
    return (db.query(AppScript)
            .filter(AppScript.project_id == project_id, AppScript.is_deleted.is_(False))
            .order_by(AppScript.id.desc()).all())


@router.get("/app-scripts/{script_id}", response_model=AppScriptOut)
def get_script(script_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return _get_script(db, current, script_id, "viewer")


@router.put("/app-scripts/{script_id}", response_model=AppScriptOut)
def update_script(script_id: int, payload: AppScriptPatch, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    s = _get_script(db, current, script_id, "editor")
    if payload.case is not None:
        _check_case(payload.case, payload.allow_high_risk)
        s.case_json = payload.case
        s.app_package = str(payload.case.get("targetAppPackage") or "")
    if payload.name is not None:
        s.name = payload.name
    if payload.description is not None:
        s.description = payload.description
    s.updated_by = current.id
    db.commit()
    db.refresh(s)
    return s


@router.delete("/app-scripts/{script_id}", status_code=204)
def delete_script(script_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    s = _get_script(db, current, script_id, "editor")
    s.is_deleted = True
    s.updated_by = current.id
    db.commit()
