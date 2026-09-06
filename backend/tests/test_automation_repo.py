# backend/tests/test_automation_repo.py
"""计划 11 Task 1:AutomationRepo 模型——字段/别名/唯一约束 与 KINDS 常量。"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import AutomationRepo, Project


@pytest.fixture()
def db(db_session):
    """conftest 提供的是 db_session;这里起别名,使测试体与 plan 稿一致。"""
    return db_session


@pytest.fixture(autouse=True)
def _clean_automation_repos():
    """conftest._TABLES 未包含 automation_repos;若不清理,projects 被 TRUNCATE
    复位自增后 id 复用,残留行会撞 uq_autorepo_project_kind。"""
    yield
    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        session.execute(text("TRUNCATE TABLE automation_repos"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        session.commit()
    finally:
        session.close()


def _mk_project(db, name="导出仓项目"):
    p = Project(name=name)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_create_repo_with_property_aliases(db):
    p = _mk_project(db)
    r = AutomationRepo(project_id=p.id, kind="web", repo_url="https://gitlab.com/g/web.git", repo_token="tok")
    db.add(r)
    db.commit()
    db.refresh(r)
    # 鸭子类型别名:git_service 直接可用
    assert r.git_repo_url == "https://gitlab.com/g/web.git"
    assert r.git_token == "tok"
    assert r.is_deleted is False


def test_unique_project_kind(db):
    p = _mk_project(db, "唯一约束项目")
    db.add(AutomationRepo(project_id=p.id, kind="web", repo_url="file:///a"))
    db.commit()
    db.add(AutomationRepo(project_id=p.id, kind="web", repo_url="file:///b"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # 同项目不同 kind 不冲突
    db.add(AutomationRepo(project_id=p.id, kind="api", repo_url="file:///c"))
    db.commit()


def test_kinds_value_set():
    from app.automation_repo import KINDS
    assert set(KINDS) == {"api", "web", "app"}
