from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
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
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")

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
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")

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
    user_prompt: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="用户补充提示词(发起生成时可选填写,随任务持久化)"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")
    artifacts: Mapped[list | None] = mapped_column(
        JSON, nullable=True, comment="接口生成产物文件清单:[{\"path\":...,\"action\":\"created|overwritten\"}];用例生成任务为NULL"
    )
    output_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="AI 流式输出全文(跨修复轮累积,终态回放用)"
    )
    thinking_text: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="AI 思考摘要全文(display=summarized,跨修复轮累积,终态回放用)"
    )
    tool_trace: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="过程记录:引擎工具调用的人类可读行(按序累积,终态回放用)"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="任务开始执行时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="任务终态(完成/失败)时间")

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


class UiScript(Base):
    __tablename__ = "ui_scripts"
    __table_args__ = {"comment": "UI自动化脚本表：录制的JSON步骤DSL，跨端中性"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="脚本主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    name: Mapped[str] = mapped_column(String(200), comment="脚本名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="脚本描述")
    script: Mapped[dict] = mapped_column(JSON, default=dict, comment="脚本DSL文档:{version,meta,variables,steps}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")
    driver_target: Mapped[str] = mapped_column(String(16), default="web", comment="端:web/android/harmony(由 script.meta.target 派生)")


class UiRun(Base):
    __tablename__ = "ui_runs"
    __table_args__ = {"comment": "UI自动化执行记录表：一次脚本回放的步骤级结果"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="执行记录主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="状态：pending/running/completed/failed")
    script_id: Mapped[int] = mapped_column(ForeignKey("ui_scripts.id"), comment="执行的脚本ID")
    script_name: Mapped[str] = mapped_column(String(200), default="", comment="执行时的脚本名快照(脚本改名/删除不影响历史)")
    mode: Mapped[str] = mapped_column(String(10), default="headless", comment="浏览器模式：headless/headed")
    variables: Mapped[dict] = mapped_column(JSON, default=dict, comment="用户传入变量覆盖值")
    step_results: Mapped[list] = mapped_column(JSON, default=list, comment="步骤结果列表:[{step_id,action,status,error,screenshot,elapsed_ms}]")
    steps_total: Mapped[int] = mapped_column(Integer, default=0, comment="总步骤数")
    steps_passed: Mapped[int] = mapped_column(Integer, default=0, comment="通过步骤数")
    steps_failed: Mapped[int] = mapped_column(Integer, default=0, comment="失败步骤数")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="整体失败原因(环境级错误,非断言失败)")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始执行时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="终态时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    driver_target: Mapped[str] = mapped_column(String(16), default="web", comment="端:web/android/harmony")
    ai_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="AI 执行用量:{input_tokens,output_tokens,cost_usd,report_path}")


class UiAuthState(Base):
    __tablename__ = "ui_auth_states"
    __table_args__ = {"comment": "UI自动化登录态表：storage_state 文件的登记行"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="登录态主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    name: Mapped[str] = mapped_column(String(200), comment="登录态名称")
    storage_path: Mapped[str] = mapped_column(String(1000), comment="storage_state JSON 文件存储路径")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")
    kind: Mapped[str] = mapped_column(String(20), default="web_storage", comment="登录态种类:web_storage/android_snapshot")
    app_package: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="应用包名(仅 android_snapshot)")


class AutomationRepo(Base):
    __tablename__ = "automation_repos"
    __table_args__ = (
        UniqueConstraint("project_id", "kind", name="uq_autorepo_project_kind"),
        {"comment": "自动化工程仓表：一项目×分类(api/web/app)各一仓,分开推送"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, comment="自动化仓主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    kind: Mapped[str] = mapped_column(String(16), comment="仓分类:api/web/app")
    repo_url: Mapped[str] = mapped_column(String(500), comment="仓库地址(http(s)/file)")
    repo_token: Mapped[str | None] = mapped_column(String(200), nullable=True, comment="访问仓库的认证 Token(明文,已接受)")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")

    # 鸭子类型别名:让本模型可直接传入 git_service(其按 project.git_repo_url/git_token 取值)
    @property
    def git_repo_url(self) -> str | None:
        return self.repo_url

    @property
    def git_token(self) -> str | None:
        return self.repo_token


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "平台用户(管理员建号,无自助注册)"}

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, comment="登录名")
    display_name: Mapped[str] = mapped_column(String(64), comment="显示名")
    password_hash: Mapped[str] = mapped_column(String(100), comment="bcrypt 哈希")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="禁用而非删除")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member"),
        {"comment": "项目成员(多对多,角色 owner/editor/viewer)"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="项目ID")
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), comment="用户ID")
    role: Mapped[str] = mapped_column(String(16), comment="owner/editor/viewer")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
