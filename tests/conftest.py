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

from app.database import Base, SessionLocal, engine
from app.main import create_app
from app.models import Case, Document, FeaturePoint, GenerationJob, Module, Project, StagedCase, Step

_TABLES = (StagedCase, GenerationJob, Step, Case, FeaturePoint, Module, Document, Project)


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


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


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c
