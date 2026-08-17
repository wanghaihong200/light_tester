from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = {"comment": "项目表：平台顶层实体，对应一个被测系统"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="项目主键ID")
    name: Mapped[str] = mapped_column(String(100), unique=True, comment="项目名称，唯一标识")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="项目描述")
    git_repo_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="关联的自动化工程 GitLab 仓库地址")
    git_token: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="访问 GitLab 仓库的认证 Token")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")

    modules: Mapped[list[Module]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    jobs: Mapped[list[GenerationJob]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Module(Base):
    __tablename__ = "modules"
    __table_args__ = {"comment": "模块表：用例树上纯粹组织性的容器节点，可任意层级嵌套"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="模块主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("modules.id"), nullable=True, comment="父模块ID，根节点为NULL"
    )
    name: Mapped[str] = mapped_column(String(200), comment="模块名称")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="同级排序序号，值越小越靠前")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")

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
    __table_args__ = {"comment": "功能点表：一个可测试的功能单元，由需求拆解而来，下辖若干用例"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="功能点主键ID")
    module_id: Mapped[int] = mapped_column(ForeignKey("modules.id"), comment="所属模块ID")
    name: Mapped[str] = mapped_column(String(200), comment="功能点名称")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="同级排序序号，值越小越靠前")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")

    module: Mapped[Module] = relationship(back_populates="feature_points")
    cases: Mapped[list[Case]] = relationship(
        back_populates="feature_point", cascade="all, delete-orphan"
    )


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = {"comment": "用例表：用例树的叶子节点，包含测试用例核心信息"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="用例主键ID")
    feature_point_id: Mapped[int] = mapped_column(ForeignKey("feature_points.id"), comment="所属功能点ID")
    title: Mapped[str] = mapped_column(String(500), comment="用例标题")
    priority: Mapped[str] = mapped_column(String(8), comment="优先级：P0(最高)/P1(中)/P2(低)")
    precondition: Mapped[str | None] = mapped_column(Text, nullable=True, comment="前置条件")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注信息")
    executed_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True, comment="执行结果：True=通过，False=失败，NULL=未执行")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="同级排序序号，值越小越靠前")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")

    feature_point: Mapped[FeaturePoint] = relationship(back_populates="cases")
    steps: Mapped[list[Step]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="Step.step_no",
    )


class Step(Base):
    __tablename__ = "steps"
    __table_args__ = {"comment": "步骤表：用例内有序的操作+预期对"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="步骤主键ID")
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), comment="所属用例ID")
    step_no: Mapped[int] = mapped_column(Integer, comment="步骤序号，从1开始递增")
    action: Mapped[str] = mapped_column(Text, comment="操作内容")
    expected: Mapped[str] = mapped_column(Text, comment="预期结果")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")

    case: Mapped[Case] = relationship(back_populates="steps")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {"comment": "文档表：项目下的Markdown文档集合，用于AI生成输入"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="文档主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    filename: Mapped[str] = mapped_column(String(300), comment="原始文件名")
    storage_path: Mapped[str] = mapped_column(String(1000), comment="文件在服务器上的存储路径")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="上传时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")

    project: Mapped[Project] = relationship(back_populates="documents")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    __table_args__ = {"comment": "生成任务表：一次AI生成的异步执行单元"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="生成任务主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True, comment="输入文档ID，可为空"
    )
    target_module_id: Mapped[int | None] = mapped_column(
        ForeignKey("modules.id"), nullable=True, comment="目标模块ID，生成产物所属位置"
    )
    job_type: Mapped[str] = mapped_column(String(50), default="case_generation", comment="任务类型：case_generation=用例生成/其他扩展类型")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="任务状态：pending=待执行/running=执行中/completed=完成/failed=失败")
    model: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="使用的AI模型名称")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输入Token消耗数量")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输出Token消耗数量")
    cost_usd: Mapped[float] = mapped_column(Float, default=0, comment="任务消耗费用(美元)")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="执行失败时的错误信息")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    artifacts: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="接口生成产物文件清单:[{\"path\":...,\"action\":\"created|overwritten\"}];用例生成任务为NULL"
    )

    project: Mapped[Project] = relationship(back_populates="jobs")
    document: Mapped[Document | None] = relationship(
        foreign_keys=[document_id], lazy="select"
    )
    target_module: Mapped[Module | None] = relationship(
        foreign_keys=[target_module_id], lazy="select"
    )
    staged: Mapped[list[StagedCase]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )

    @property
    def document_name(self) -> str | None:
        """返回关联文档的文件名,若无文档则返回 None"""
        return self.document.filename if self.document else None


class StagedCase(Base):
    __tablename__ = "staged_cases"
    __table_args__ = {"comment": "暂存区用例表：生成任务的用例产物在确认入库前的存放地"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="暂存用例主键ID")
    job_id: Mapped[int] = mapped_column(ForeignKey("generation_jobs.id"), comment="所属生成任务ID")
    feature_point_name: Mapped[str] = mapped_column(String(200), comment="功能点名称(入库时用于匹配或创建功能点)")
    title: Mapped[str] = mapped_column(String(500), comment="用例标题")
    priority: Mapped[str] = mapped_column(String(8), comment="优先级：P0(最高)/P1(中)/P2(低)")
    precondition: Mapped[str | None] = mapped_column(Text, nullable=True, comment="前置条件")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True, comment="备注信息")
    steps: Mapped[list] = mapped_column(JSON, default=list, comment="步骤列表(JSON格式，每项包含action和expected)")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")

    job: Mapped[GenerationJob] = relationship(back_populates="staged")
