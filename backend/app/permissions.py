"""项目级角色闸门:404 不可见 / 403 角色不足 / admin 直通。"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import ProjectMember, User

ROLE_LEVEL = {"viewer": 0, "editor": 1, "owner": 2}


def user_role_in_project(db: Session, user: User, project_id: int) -> str | None:
    if user.is_admin:
        return "owner"
    row = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        .first()
    )
    return row.role if row else None


def ensure_project_access(db: Session, user: User, project_id: int, min_role: str = "viewer") -> None:
    role = user_role_in_project(db, user, project_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    if ROLE_LEVEL.get(role, -1) < ROLE_LEVEL[min_role]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "无项目操作权限")


def visible_project_ids(db: Session, user: User) -> list[int] | None:
    if user.is_admin:
        return None
    rows = db.query(ProjectMember.project_id).filter(ProjectMember.user_id == user.id).all()
    return [r[0] for r in rows]
