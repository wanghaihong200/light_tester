# 项目成员管理:列表(viewer+)可读协作,添加/改角色/移除(owner+);末位 owner 不可动(admin 同受约束)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import ProjectMember, User
from app.permissions import ensure_project_access
from app.schemas_auth import MemberAddIn, MemberOut, MemberRoleUpdate

router = APIRouter(prefix="/api/projects", tags=["members"], dependencies=[Depends(get_current_user)])


def _owner_count_without(db: Session, project_id: int, member_id: int) -> int:
    """若目标成员不再是 owner,项目剩余 owner 数(末位 owner 守卫用)。"""
    return (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project_id,
            ProjectMember.role == "owner",
            ProjectMember.id != member_id,
        )
        .count()
    )


def _get_member(db: Session, project_id: int, user_id: int) -> ProjectMember:
    row = db.query(ProjectMember).filter_by(project_id=project_id, user_id=user_id).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    return row


def _to_out(row: ProjectMember, user: User) -> MemberOut:
    # MemberOut 平铺 User 字段(join 出 username/display_name)
    return MemberOut(
        id=row.id, user_id=row.user_id, role=row.role,
        username=user.username, display_name=user.display_name,
    )


@router.get("/{project_id}/members", response_model=list[MemberOut])
def list_members(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")  # 看得到队友才好协作
    pairs = (
        db.query(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .filter(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.id)
        .all()
    )
    return [_to_out(row, user) for row, user in pairs]


@router.post("/{project_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def add_member(
    project_id: int, payload: MemberAddIn, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    ensure_project_access(db, current, project_id, "owner")  # 权限闸先于用户存在性检查
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if db.query(ProjectMember).filter_by(project_id=project_id, user_id=user.id).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "已是项目成员")
    row = ProjectMember(project_id=project_id, user_id=user.id, role=payload.role)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row, user)


@router.put("/{project_id}/members/{user_id}", response_model=MemberOut)
def update_member_role(
    project_id: int, user_id: int, payload: MemberRoleUpdate,
    db: Session = Depends(get_db), current: User = Depends(get_current_user),
):
    ensure_project_access(db, current, project_id, "owner")
    row = _get_member(db, project_id, user_id)
    # 降级 owner 前守卫:剩余 owner 不得归零(admin 直通角色闸,但同样留不住这条不变式)
    if row.role == "owner" and payload.role != "owner" and _owner_count_without(db, project_id, row.id) == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "项目至少需要一名 owner")
    row.role = payload.role
    db.commit()
    db.refresh(row)
    return _to_out(row, db.get(User, row.user_id))


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    project_id: int, user_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    ensure_project_access(db, current, project_id, "owner")
    row = _get_member(db, project_id, user_id)
    if row.role == "owner" and _owner_count_without(db, project_id, row.id) == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "项目至少需要一名 owner")
    db.delete(row)
    db.commit()
