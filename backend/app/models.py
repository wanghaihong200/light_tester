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


class AppScript(Base):
    __tablename__ = "app_scripts"
    __table_args__ = {"comment": "APP自动化脚本表：SoloPi 原生用例 JSON 唯一事实源"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="脚本主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    name: Mapped[str] = mapped_column(String(200), comment="脚本名称(平台展示名;用例名 caseName 在 case_json 内)")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="脚本描述")
    case_json: Mapped[dict] = mapped_column(JSON, comment="SoloPi 原生用例 JSON,原样存储(caseName/targetAppPackage/operationLog.steps…)")
    app_package: Mapped[str] = mapped_column(String(200), default="", comment="被测应用包名(case_json.targetAppPackage 派生,便于列表展示)")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")


class AppRun(Base):
    __tablename__ = "app_runs"
    __table_args__ = {"comment": "APP自动化执行记录表：一次 SoloPi 用例回放(单设备一行,批量=多行同 batch_id)"}

    id: Mapped[int] = mapped_column(primary_key=True, comment="执行记录主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    status: Mapped[str] = mapped_column(String(20), default="pending", comment="状态：pending/running/passed/failed/cancelled")
    script_id: Mapped[int] = mapped_column(ForeignKey("app_scripts.id"), comment="执行的脚本ID")
    script_name: Mapped[str] = mapped_column(String(200), default="", comment="执行时的脚本名快照(脚本改名/删除不影响历史)")
    device_serial: Mapped[str] = mapped_column(String(100), comment="设备序列号(adb serial)")
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, comment="分发批量执行分组 UUID;单设备执行为 NULL")
    variables: Mapped[dict] = mapped_column(JSON, default=dict, comment="运行参数(Phase 1 预留不消费)")
    pre_checks: Mapped[list] = mapped_column(JSON, default=list, comment="前置检查点定义列表(inspect 自判)")
    post_checks: Mapped[list] = mapped_column(JSON, default=list, comment="后置检查点定义列表(inspect 自判)")
    perf_items: Mapped[list] = mapped_column(JSON, default=list, comment="perf 采集项(CPU/FPS/Memory 等,以 perf-list 动态发现为准)")
    run_state: Mapped[str | None] = mapped_column(String(20), nullable=True, comment="CLI runId 终态快照:passed/failed/cancelled")
    results: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="harness results[](失败含 exceptionMessage/exceptionStep/exceptionStepId)")
    check_results: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment='检查点结果:{"pre":[…],"post":[…]}')
    perf_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="perf-analyze 描述性统计(逐列 min/max/mean/median/p90)")
    startup_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="startup-time 统计(LaunchState/ThisTime/TotalTime/WaitTime)")
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="失败原因(环境级错误或检查点未通过)")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始执行时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="终态时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")


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


class MockInstance(Base):
    __tablename__ = "mock_instances"
    __table_args__ = (UniqueConstraint("port", name="uq_mock_instance_port"),
                      {"comment": "Mock服务实例表：项目下可多个,一实例=一独立进程+端口=一 base_url"})
    id: Mapped[int] = mapped_column(primary_key=True, comment="实例主键ID")
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    name: Mapped[str] = mapped_column(String(200), comment="实例名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="实例描述")
    port: Mapped[int] = mapped_column(Integer, comment="监听端口(全局唯一,含软删行=端口预留)")
    token: Mapped[str] = mapped_column(String(64), comment="实例令牌(uuid hex):健康/关停端点鉴权+孤儿识别")
    cors_enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="CORS 放行:* 头+OPTIONS 预检直放")
    default_status: Mapped[int] = mapped_column(Integer, default=404, comment="无命中兜底状态码")
    default_body: Mapped[str | None] = mapped_column(Text, nullable=True, comment="无命中兜底响应体(空则用内置 JSON)")
    passthrough_enabled: Mapped[bool] = mapped_column(Boolean, default=False,
        comment="透传开关:未命中时转发原始请求到上游真实服务(计划 15)")
    upstream_base_url: Mapped[str | None] = mapped_column(String(500), nullable=True,
        comment="上游真实服务 base_url,如 http://real-api:8080;透传开启时必填")
    desired: Mapped[str] = mapped_column(String(16), default="stopped", comment="期望状态:running/stopped(声明式)")
    status: Mapped[str] = mapped_column(String(16), default="stopped", comment="实际状态:stopped/starting/running/error")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="error 态原因")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")


class MockRuleGroup(Base):
    __tablename__ = "mock_rule_groups"
    __table_args__ = {"comment": "规则组表:实例内 method+路径模板 相同的规则的容器,"
                                 "以「METHOD / 路径」命名,组间+组内两级有序匹配(ADR-0011)"}
    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("mock_instances.id"))
    method: Mapped[str] = mapped_column(String(10), comment="HTTP 方法(大写),组级")
    path_template: Mapped[str] = mapped_column(String(500), comment="路径:精确或 /a/{var} 模板,组级")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="规则组描述(可空)")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="组级停用=整组不参与匹配")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="组间排序,小者先匹配")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")


class MockRule(Base):
    __tablename__ = "mock_rules"
    __table_args__ = {"comment": "Mock规则表：实例内有序的匹配条件组→响应定义,第一条命中生效"}
    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("mock_instances.id"))
    group_id: Mapped[int] = mapped_column(ForeignKey("mock_rule_groups.id"),
        comment="所属规则组;method/path 由组承载,规则只存条件+响应")
    conditions: Mapped[list] = mapped_column(JSON, default=list,
        comment='条件行:[{scope:"query|header|body", key, match:"eq|regex", value}];AND 语义')
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, comment="停用规则不参与匹配")
    response_status: Mapped[int] = mapped_column(Integer, default=200, comment="响应状态码(100-599)")
    response_headers: Mapped[dict] = mapped_column(JSON, default=dict, comment="响应头 kv")
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True, comment="响应体(可含模板)")
    enable_template: Mapped[bool] = mapped_column(Boolean, default=False, comment="响应体启用 Jinja2 模板渲染")
    delay_ms: Mapped[int] = mapped_column(Integer, default=0, comment="固定延迟毫秒")
    timeout_enabled: Mapped[bool] = mapped_column(Boolean, default=False, comment="模拟超时:挂住不回")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=30, comment="模拟超时挂住秒数(1-3600)")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="组内排序,小者先匹配")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间"
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已删除(软删除标记)")
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="创建人 users.id")
    updated_by: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="最后修改人 users.id")


class MockHit(Base):
    __tablename__ = "mock_hits"
    __table_args__ = {"comment": "命中记录表：打到实例的请求及处理结果(append-only,清空=硬删)"}
    id: Mapped[int] = mapped_column(primary_key=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("mock_instances.id"))
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("mock_rules.id"), nullable=True, comment="命中的规则;NULL=未命中走兜底")
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(500))
    query: Mapped[str | None] = mapped_column(String(1000), nullable=True, comment="原始 query 串(无 ?)")
    request_headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_body: Mapped[str | None] = mapped_column(Text, nullable=True, comment="截断 64KB 的 utf-8 摘录")
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True,
        comment="实际响应体(mock 渲染结果/上游真响应/兜底体;64KB 截断 utf-8 摘录)")
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[str] = mapped_column(String(16), default="fallback",
        comment="结局:matched(规则响应)/fallback(兜底)/forwarded(透传);透传失败落兜底仍为 fallback,原因入 error")
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="回写状态码(超时挂住=规则状态)")
    delay_ms: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True, comment="如 timeout-simulated")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PerfRecord(Base):
    __tablename__ = "perf_records"
    __table_args__ = (
        UniqueConstraint("source", "source_ref", name="uq_perf_source_ref"),
        {"comment": "性能记录表:run=APP自动化执行引用行 / import=设备端历史导入(ADR-0010)"},
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), comment="所属项目ID")
    source: Mapped[str] = mapped_column(String(20), comment="来源:run/import")
    name: Mapped[str] = mapped_column(String(200), default="", comment="展示名(run=脚本名@设备,import=导入命名)")
    app_run_id: Mapped[int | None] = mapped_column(ForeignKey("app_runs.id"), nullable=True, comment="run 来源的执行记录ID(import 为 NULL)")
    script_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="脚本ID快照(run 来源,趋势分组用)")
    script_name: Mapped[str] = mapped_column(String(200), default="", comment="脚本名快照")
    device_serial: Mapped[str] = mapped_column(String(100), default="", comment="设备序列号")
    perf_items: Mapped[list] = mapped_column(JSON, default=list, comment="采集项清单(import=metrics)")
    source_ref: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="import=设备端历史id(唯一防重复导入);run 为 NULL")
    data_complete: Mapped[bool] = mapped_column(Boolean, default=True, comment="数据完整性(import preview 截断=False)")
    perf_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="描述性统计(columns[].index/min/max/mean/median/p90)")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="采集开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="采集结束时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
