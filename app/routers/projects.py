from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Project, ProjectMember, User
from app.permissions import ensure_project_access, visible_project_ids
from app.schemas import ProjectCreate, ProjectOut, ProjectUpdate
from app.excel_export import build_excel_bytes
from app.xmind_export import build_xmind_bytes

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(get_current_user)])


def _get_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ids = visible_project_ids(db, current)
    q = db.query(Project).order_by(Project.id)
    return q.filter(Project.id.in_(ids)).all() if ids is not None else q.all()


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if db.query(Project).filter(Project.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "project name already exists")
    project = Project(**payload.model_dump(), created_by=current.id)  # 建时不写 updated_by,仅 update 时写
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=current.id, role="owner"))
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    return _get_or_404(db, project_id)


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(
    project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    ensure_project_access(db, current, project_id, "editor")
    project = _get_or_404(db, project_id)
    data = payload.model_dump(exclude_unset=True)
    if "name" in data:
        existing = db.query(Project).filter(Project.name == data["name"], Project.id != project_id).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "project name already exists")
    for field, value in data.items():
        setattr(project, field, value)
    project.updated_by = current.id
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "owner")
    project = _get_or_404(db, project_id)
    # 先清成员行,否则 project_members.project_id 外键会挡住项目删除(1451)
    db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete()
    db.delete(project)
    db.commit()


@router.get("/{project_id}/export/xmind")
def export_xmind(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    project = _get_or_404(db, project_id)
    payload = build_xmind_bytes(db, project)
    filename = quote(f"{project.name}.xmind")  # RFC 5987,支持中文项目名
    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.get("/{project_id}/export/excel")
def export_excel(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    project = _get_or_404(db, project_id)
    payload = build_excel_bytes(db, project)
    filename = quote(f"{project.name}.xlsx")  # RFC 5987,支持中文项目名
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
