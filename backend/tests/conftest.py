import os

os.environ.setdefault(
    "DATABASE_URL",
    "mysql+pymysql://root:root123@127.0.0.1:3307/test_platform_test?charset=utf8mb4",
)

# 强制清空 AI API key,防止用户 .env 填真 key 后跑 pytest 启动真 worker 烧钱
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.main import create_app
from app.models import (
    Case, CiRun, Document, ExecutionPlan, FeaturePoint, GenerationJob, InterfaceCase,
    JenkinsConnection, MockHit, MockInstance, MockRule, MockRuleGroup, Module, Project,
    ProjectMember, StagedCase, Step, UiAuthState, UiRun, UiScript, User,
)

_TABLES = (StagedCase, GenerationJob, Step, Case, FeaturePoint, Module, Document, Project, UiRun, UiScript, UiAuthState, User, MockHit, MockInstance, MockRule, MockRuleGroup, ProjectMember, CiRun, ExecutionPlan, InterfaceCase, JenkinsConnection)


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def _isolate_app_data(tmp_path_factory):
    """所有测试的 app_data_dir 指向临时目录——真实 data/app 永不被测试读写/清理
    (2026-09-10 事故:并行 pytest 的清理 fixture 删光用户冒烟数据 runs/*/perf)。
    settings 为单例,直接改属性并在用例后还原,防止污染其他域测试。"""
    real = settings.app_data_dir
    settings.app_data_dir = tmp_path_factory.mktemp("app_data")
    yield
    settings.app_data_dir = real


@pytest.fixture(autouse=True)
def _isolate_ci_data(tmp_path_factory):
    """同 _isolate_app_data:ci_data_dir 指向临时目录——真实 data/ci 永不被测试读写
    (计划 16 T11 会写 runs/{run_id}/console.log,不隔离会污染真实目录)。"""
    real = settings.ci_data_dir
    settings.ci_data_dir = tmp_path_factory.mktemp("ci_data")
    yield
    settings.ci_data_dir = real


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    db = SessionLocal()
    try:
        # Use TRUNCATE for cleaner reset (resets auto-increment and avoids FK issues)
        db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in reversed(_TABLES):  # Reverse order helps with some FKs
            db.execute(text(f"TRUNCATE TABLE {table.__tablename__}"))
        db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        db.commit()
    finally:
        db.close()
    # 进程内全局态与 DB 一起复位:TRUNCATE 复位自增后 run id 会被复用,
    # 残留的强制结束标记会让下个用例的 run 在第一步被 ForceCancelled 静默放行(状态停 running)。
    from app.ui_automation import runner

    runner._force_finished.clear()


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture()
def db_session():
    db = SessionLocal()
    try:
        yield db
        db.rollback()
    finally:
        db.close()


@pytest.fixture()
def make_user():
    from app.auth import hash_password

    def _make(db: Session, username: str, *, is_admin: bool = False):
        u = User(
            username=username,
            display_name=username,
            password_hash=hash_password("pw-" + username),
            is_admin=is_admin,
        )
        db.add(u)
        db.commit()
        return u

    return _make
