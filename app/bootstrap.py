"""首个 admin 的启动引导:users 无 is_admin 行则建 admin/admin123(内网,首登后自行改密)。"""
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import User


def ensure_bootstrap_admin(db: Session) -> User:
    admin = db.query(User).filter(User.is_admin.is_(True)).first()
    if admin is not None:
        return admin
    admin = User(
        username="admin",
        display_name="管理员",
        password_hash=hash_password("admin123"),
        is_admin=True,
    )
    db.add(admin)
    db.commit()
    return admin
