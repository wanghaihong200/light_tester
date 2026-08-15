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
