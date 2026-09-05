# UI自动化脚本 CRUD:录制产出的步骤 DSL 文档的增删改查
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Project, UiScript, User
from app.permissions import ensure_project_access
from app.schemas import UiScriptOut, UiScriptSave

router = APIRouter(prefix="/api", tags=["ui-scripts"], dependencies=[Depends(get_current_user)])


def _get_owned(db: Session, current: User, script_id: int, min_role: str) -> UiScript:
    # 软删后的行对外视为不存在,与列表口径一致;取行后按所属项目过角色闸门
    row = db.get(UiScript, script_id)
    if row is None or row.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ui script not found")
    ensure_project_access(db, current, row.project_id, min_role)
    return row


@router.post("/projects/{project_id}/ui-scripts", response_model=UiScriptOut, status_code=status.HTTP_201_CREATED)
def create_script(project_id: int, payload: UiScriptSave, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    ensure_project_access(db, current, project_id, "editor")  # 建脚本 = 写
    row = UiScript(project_id=project_id, **payload.model_dump(), created_by=current.id)  # updated_by 仅 update 时写
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/projects/{project_id}/ui-scripts", response_model=list[UiScriptOut])
def list_scripts(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    return (
        db.query(UiScript)
        .filter(UiScript.project_id == project_id, UiScript.is_deleted.is_(False))
        .order_by(UiScript.id.desc())
        .all()
    )


@router.get("/ui-scripts/{script_id}", response_model=UiScriptOut)
def get_script(script_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return _get_owned(db, current, script_id, "viewer")


@router.put("/ui-scripts/{script_id}", response_model=UiScriptOut)
def update_script(script_id: int, payload: UiScriptSave, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    row = _get_owned(db, current, script_id, "editor")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    row.updated_by = current.id
    db.commit()
    db.refresh(row)
    return row


@router.delete("/ui-scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_script(script_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    row = _get_owned(db, current, script_id, "editor")
    # 软删:ui_runs.script_id 外键历史必须不断链,禁止物理 delete
    row.is_deleted = True
    db.commit()
