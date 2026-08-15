### Task 2: 数据模型 + 项目 CRUD

**Files:**
- Create: `test-platform/backend/app/models.py`
- Create: `test-platform/backend/app/schemas.py`
- Create: `test-platform/backend/app/routers/__init__.py`
- Create: `test-platform/backend/app/routers/projects.py`
- Modify: `test-platform/backend/app/main.py`(注册路由)
- Modify: `test-platform/backend/tests/conftest.py`(加 client/db fixture)
- Test: `test-platform/backend/tests/test_projects.py`

**Interfaces:**
- Consumes: Task 1 的 `create_app()`、`get_db()`、`Base`。
- Produces: ORM 模型 `Project / Module / FeaturePoint / Case / Step / Document`(本任务只用到 Project,但模型一次写全);REST:`GET /api/projects`、`POST /api/projects`、`GET /api/projects/{id}`、`PUT /api/projects/{id}`、`DELETE /api/projects/{id}`;Pydantic 模型 `ProjectCreate / ProjectUpdate / ProjectOut`;conftest 提供 `client` fixture(`TestClient`)与 `db` fixture。Task 3-5 依赖这些模型与 fixture。

- [ ] **Step 1: 写 models.py(全部六张表一次到位)**

`test-platform/backend/app/models.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    git_repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    git_token: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    modules: Mapped[list[Module]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("modules.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="modules")
    parent: Mapped[Module | None] = relationship(
        "Module", remote_side="Module.id", back_populates="children"
    )
    children: Mapped[list[Module]] = relationship(
        back_populates="parent", cascade="all, delete-orphan"
    )
    feature_points: Mapped[list[FeaturePoint]] = relationship(
        back_populates="module", cascade="all, delete-orphan"
    )


class FeaturePoint(Base):
    __tablename__ = "feature_points"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"))
    name: Mapped[str] = mapped_column(String(200))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    module: Mapped[Module] = relationship(back_populates="feature_points")
    cases: Mapped[list[Case]] = relationship(
        back_populates="feature_point", cascade="all, delete-orphan"
    )


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature_point_id: Mapped[int] = mapped_column(ForeignKey("feature_points.id"))
    title: Mapped[str] = mapped_column(String(500))
    priority: Mapped[str] = mapped_column(String(8))  # P0 / P1 / P2
    precondition: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    feature_point: Mapped[FeaturePoint] = relationship(back_populates="cases")
    steps: Mapped[list[Step]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Step.step_no",
    )


class Step(Base):
    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    step_no: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(Text)
    expected: Mapped[str] = mapped_column(Text)

    case: Mapped[Case] = relationship(back_populates="steps")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    filename: Mapped[str] = mapped_column(String(300))
    storage_path: Mapped[str] = mapped_column(String(1000))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped[Project] = relationship(back_populates="documents")
```

- [ ] **Step 2: 写 schemas.py(项目部分)**

`test-platform/backend/app/schemas.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Priority = Literal["P0", "P1", "P2"]


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    git_repo_url: str | None = None
    git_token: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    git_repo_url: str | None = None
    git_token: str | None = None


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    git_repo_url: str | None
    created_at: datetime
```

- [ ] **Step 3: 写项目路由**

`test-platform/backend/app/routers/projects.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.schemas import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_or_404(db: Session, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.query(Project).order_by(Project.id).all()


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    if db.query(Project).filter(Project.name == payload.name).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "project name already exists")
    project = Project(**payload.model_dump())
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    return _get_or_404(db, project_id)


@router.put("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = _get_or_404(db, project_id)
    db.delete(project)
    db.commit()
```

Modify `app/main.py`(注册路由,health 保留):

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import projects


def create_app() -> FastAPI:
    app = FastAPI(title="test-platform")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(projects.router)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: 扩展 conftest.py(建表 + 清库 + client fixture)**

`test-platform/backend/tests/conftest.py` 整体替换为:

```python
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
```

- [ ] **Step 5: 写失败测试**

`test-platform/backend/tests/test_projects.py`:

```python
def test_create_and_get_project(client):
    resp = client.post(
        "/api/projects", json={"name": "商城系统", "description": "被测系统A"}
    )
    assert resp.status_code == 201
    pid = resp.json()["id"]

    resp = client.get(f"/api/projects/{pid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "商城系统"
    assert "git_token" not in body  # 列表/详情不回显 token


def test_duplicate_name_rejected(client):
    client.post("/api/projects", json={"name": "P"})
    resp = client.post("/api/projects", json={"name": "P"})
    assert resp.status_code == 409


def test_update_project(client):
    pid = client.post("/api/projects", json={"name": "old"}).json()["id"]
    resp = client.put(
        f"/api/projects/{pid}",
        json={"name": "new", "git_repo_url": "http://gitlab.example/repo.git"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new"


def test_delete_project(client):
    pid = client.post("/api/projects", json={"name": "bye"}).json()["id"]
    assert client.delete(f"/api/projects/{pid}").status_code == 204
    assert client.get(f"/api/projects/{pid}").status_code == 404
```

- [ ] **Step 6: 跑测试确认通过**

```bash
pytest tests/test_projects.py -v
```

Expected: 4 passed。

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "feat: project model and CRUD API"
```

---

