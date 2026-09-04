# 用户管理(admin only):建号/列表/改资料·重置密码·禁用;不能操作自己的账号(禁用或降级自己)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password
from app.database import get_db
from app.models import User
from app.schemas_auth import UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(get_current_user)])


def _require_admin(current: User) -> None:
    """路由级 Depends(get_current_user) 只保证已登录;admin 闸在此(非 admin 403)。"""
    if not current.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要管理员权限")


@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _require_admin(current)
    return db.query(User).order_by(User.id).all()


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
    # 自操作守卫先于字段判断:禁用/降级/改自己的账号一律 409(包括只改 display_name)
    if user.id == current.id:
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
