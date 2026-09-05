# 用户管理(admin only):建号/列表/改资料·重置密码·禁用;不能禁用自己的账号(改名/自改密放行)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password
from app.database import get_db
from app.models import Project, ProjectMember, User
from app.schemas_auth import UserCreate, UserOut, UserProjectRole, UserSearchItem, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(get_current_user)])


def _require_admin(current: User) -> None:
    """路由级 Depends(get_current_user) 只保证已登录;admin 闸在此(非 admin 403)。"""
    if not current.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_admin(current)
    return db.query(User).order_by(User.id).all()


@router.get("/search", response_model=list[UserSearchItem])
def search_users(
    q: str = "",
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """用户名/显示名模糊搜索(登录即可用);供选人场景消费。"""
    kw = (q or "").strip()
    if not kw:
        return []
    limit = max(1, min(limit, 50))
    rows = (
        db.query(User)
        .filter(or_(User.username.contains(kw), User.display_name.contains(kw)))
        .order_by(User.username)
        .limit(limit)
        .all()
    )
    return [UserSearchItem(id=r.id, username=r.username, display_name=r.display_name) for r in rows]


@router.get("/{user_id}/projects", response_model=list[UserProjectRole])
def list_user_projects(
    user_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """某用户的项目授权列表(admin only;用户管理页授权弹窗消费)。"""
    _require_admin(current)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    rows = (
        db.query(ProjectMember, Project.name)
        .join(Project, Project.id == ProjectMember.project_id)
        .filter(ProjectMember.user_id == user_id)
        .order_by(Project.name)
        .all()
    )
    return [UserProjectRole(project_id=pm.project_id, project_name=name, role=pm.role) for pm, name in rows]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate, db: Session = Depends(get_db), current: User = Depends(get_current_user)
):
    _require_admin(current)
    if db.query(User).filter(User.username == payload.username).first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "用户名已存在")
    user = User(
        username=payload.username,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        is_admin=payload.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, payload: UserUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user),
):
    _require_admin(current)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    # 自操作守卫:仅拦禁用自己(payload 带 is_active 即 409),防自断门禁;
    # 改显示名/重置自己密码放行(自改密不吊销当前 token,Q6 已拍板)
    if user.id == current.id and payload.is_active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "不能操作自己的账号")
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.password is not None:  # 重置密码;旧 token 不吊销(Q6 已拍板)
        user.password_hash = hash_password(payload.password)
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user
