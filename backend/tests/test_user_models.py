from sqlalchemy.orm import Session

from app.bootstrap import ensure_bootstrap_admin
from app.models import Project, ProjectMember, User


def test_bootstrap_creates_admin_once(db_session: Session):
    u1 = ensure_bootstrap_admin(db_session)
    assert u1.is_admin and u1.is_active
    from app.auth import verify_password
    assert verify_password("admin123", u1.password_hash)
    u2 = ensure_bootstrap_admin(db_session)
    assert u2.id == u1.id  # 幂等:第二次不再建


def test_project_member_unique(db_session: Session, make_user):
    p = Project(name="m1")
    db_session.add(p)
    db_session.flush()
    u = make_user(db_session, "alice")
    db_session.add(ProjectMember(project_id=p.id, user_id=u.id, role="owner"))
    db_session.commit()
    import pytest
    from sqlalchemy.exc import IntegrityError
    db_session.add(ProjectMember(project_id=p.id, user_id=u.id, role="viewer"))
    with pytest.raises(IntegrityError):
        db_session.commit()
