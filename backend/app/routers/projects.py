from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.automation_repo import resolve_repo, upsert_repo
from app.database import get_db
from app.models import AutomationRepo, Project, ProjectMember, User
from app.permissions import ensure_project_access, visible_project_ids
from app.schemas import ProjectCreate, ProjectOut, ProjectUpdate
from app.excel_export import build_excel_bytes
from app.xmind_export import build_xmind_bytes

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(get_current_user)])

# Project 上停写的两个旧列(plan11 写透后唯一事实源是 AutomationRepo kind=api 行,列保留兼容历史数据)
_LEGACY_GIT_FIELDS = ("git_repo_url", "git_token")


def _get_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


def _project_out(db: Session, p: Project) -> dict:
    """ProjectOut 组装:git_repo_url 改从 AutomationRepo(kind=api) 行读出(前端零改动)。
    无 api 仓行(建项目时未配 git 字段)→ None,不回退 Project 旧列(方案 B 严格存储)。"""
    api_repo = resolve_repo(db, p.id, "api")
    out = ProjectOut.model_validate(p).model_dump()
    out["git_repo_url"] = api_repo.repo_url if api_repo else None
    return out


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ids = visible_project_ids(db, current)
    q = db.query(Project).order_by(Project.id)
    rows = q.filter(Project.id.in_(ids)).all() if ids is not None else q.all()
    return [_project_out(db, p) for p in rows]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if db.query(Project).filter(Project.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "project name already exists")
    # plan11 写透:git 两字段不落 Project 旧列,改写 AutomationRepo(kind=api) 行;两字段都缺省则不建行
    payload_data = {k: v for k, v in payload.model_dump().items() if k not in _LEGACY_GIT_FIELDS}
    project = Project(**payload_data, created_by=current.id)  # 建时不写 updated_by,仅 update 时写
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=current.id, role="owner"))
    if payload.git_repo_url is not None or payload.git_token is not None:
        upsert_repo(db, project.id, "api", payload.git_repo_url, payload.git_token, current.id)
    db.commit()
    db.refresh(project)
    return _project_out(db, project)


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    return _project_out(db, _get_or_404(db, project_id))


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
    # plan11 写透:git 两字段从旧列赋值中摘出,改写 AutomationRepo(kind=api) 行。
    # 任一字段出现即写透;空串/显式 null = 清空;未出现的字段保留原值(exclude_unset 语义,前端依赖)。
    url_given = "git_repo_url" in data
    token_given = "git_token" in data
    new_url = data.pop("git_repo_url", None)
    new_token = data.pop("git_token", None)
    for field, value in data.items():
        setattr(project, field, value)
    project.updated_by = current.id
    if url_given or token_given:
        existing_repo = resolve_repo(db, project_id, "api")
        upsert_repo(
            db,
            project_id,
            "api",
            new_url if url_given else (existing_repo.repo_url if existing_repo else None),
            new_token if token_given else (existing_repo.repo_token if existing_repo else None),
            current.id,
        )
    db.commit()
    db.refresh(project)
    return _project_out(db, project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "owner")
    project = _get_or_404(db, project_id)
    # 先清成员行,否则 project_members.project_id 外键会挡住项目删除(1451)
    db.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete()
    # plan11 写透:automation_repos.project_id 同样外键指向项目,先清仓行再删(1451)
    db.query(AutomationRepo).filter(AutomationRepo.project_id == project_id).delete()
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
