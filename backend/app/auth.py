"""登录安全基元:bcrypt 口令哈希与 JWT 签发/解析(HS256,7 天)。
共识:单 token 无 refresh 无服务端吊销;禁用即时生效(is_active 逐请求校验,残留见 DEFER #63)。"""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(days=settings.jwt_exp_days)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _encode(payload: dict) -> str:  # 测试钩子:构造过期 token
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> int:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return int(payload["sub"])


def get_current_user(request: Request, db: Session = Depends(get_db)) -> "User":
    """Bearer 鉴权依赖:401=未带/无效 token 或用户已不存在;403=已禁用。"""
    from app.models import User  # 局部 import 防循环

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录或登录已过期")
    try:
        user_id = decode_token(auth.removeprefix("Bearer ").strip())
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录或登录已过期")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录或登录已过期")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已禁用")
    return user


def get_current_user_sse(
    request: Request,
    token: str | None = None,
    db: Session = Depends(get_db),
) -> "User":
    """SSE 端点专用:裸 EventSource 不能带自定义头,退而支持 query ?token=。
    先头后参;两者皆无/皆无效 → 401。"""
    from app.models import User

    auth = request.headers.get("Authorization", "")
    raw = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else (token or "")
    if raw:
        try:
            user = db.get(User, decode_token(raw))
        except jwt.PyJWTError:
            user = None
        if user is not None:
            if not user.is_active:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "账号已禁用")
            return user
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录或登录已过期")
