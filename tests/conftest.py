import os

os.environ.setdefault(
    "DATABASE_URL",
    "mysql+pymysql://root:root123@127.0.0.1:3307/test_platform_test?charset=utf8mb4",
)

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import create_app
from app.models import Case, Document, FeaturePoint, Module, Project, Step

_TABLES = (Step, Case, FeaturePoint, Module, Document, Project)


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
        for table in _TABLES:
            db.query(table).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        yield c
