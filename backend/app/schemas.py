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


class FeaturePointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class FeaturePointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    module_id: int


class StepIn(BaseModel):
    action: str = Field(min_length=1)
    expected: str = Field(min_length=1)


class StepOut(StepIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step_no: int


class CaseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    priority: Priority
    precondition: str | None = None
    remark: str | None = None
    steps: list[StepIn] = Field(default_factory=list)


class CaseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    priority: Priority | None = None
    precondition: str | None = None
    remark: str | None = None
    steps: list[StepIn] | None = None


class CaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    feature_point_id: int
    title: str
    priority: Priority
    precondition: str | None
    remark: str | None
    executed_pass: bool | None
    steps: list[StepOut]


class GenerationJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    document_id: int | None
    target_module_id: int | None
    job_type: str
    status: str
    model: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    error: str | None
    created_at: datetime
    document_name: str | None
    artifacts: list[dict] | None
    output_text: str | None = None
    thinking_text: str | None = None
    user_prompt: str | None = None
    tool_trace: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class StagedCaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    feature_point_name: str
    title: str
    priority: str
    precondition: str | None
    remark: str | None
    steps: list
    created_at: datetime


# UI自动化脚本:录制的步骤 DSL JSON 文档({version,meta,variables,steps})
class UiScriptSave(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    script: dict


class UiScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str | None
    script: dict
    driver_target: str  # 端:web/android/harmony(服务端由 script.meta.target 派生)
    created_at: datetime
    updated_at: datetime


# UI自动化登录态:storage_state 文件的登记行(路径/软删标记不外泄)
class UiAuthStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    kind: str
    app_package: str | None
    created_at: datetime


# UI自动化执行记录:一次脚本回放的步骤级结果
class UiRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    status: str
    script_id: int
    script_name: str
    mode: str
    variables: dict
    step_results: list
    steps_total: int
    steps_passed: int
    steps_failed: int
    error: str | None
    driver_target: str  # 端:web/android/harmony
    ai_usage: dict | None  # AI 执行用量:{input_tokens,output_tokens,cost_usd,report_path}
    started_at: datetime | None
    finished_at: datetime | None


# APP自动化脚本:SoloPi 原生用例 JSON 唯一事实源(计划 12,独立域)
class AppScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: str | None
    case_json: dict
    app_package: str
    created_at: datetime
    updated_at: datetime


# APP自动化执行记录:单设备一行,分发批量=多行同 batch_id
class AppRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    status: str
    script_id: int
    script_name: str
    device_serial: str
    batch_id: str | None
    variables: dict
    pre_checks: list
    post_checks: list
    perf_items: list
    run_state: str | None
    results: list | None
    check_results: dict | None
    perf_summary: dict | None
    startup_summary: dict | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None


# 性能记录:run=APP自动化执行引用行 / import=设备端历史导入(计划 14 / ADR-0010)
class PerfRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    source: str
    source_ref: str | None = None  # import=设备端历史id(计划14 Task5 导入契约)
    name: str
    app_run_id: int | None = None
    script_id: int | None = None
    script_name: str
    device_serial: str
    perf_items: list[str] = Field(default_factory=list)
    data_complete: bool = True
    perf_summary: dict | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class MockCondition(BaseModel):
    scope: Literal["query", "header", "body"]
    key: str
    match: Literal["eq", "regex"] = "eq"
    value: str


class MockInstanceSave(BaseModel):
    name: str
    description: str | None = None
    port: int | None = Field(None, ge=1, le=65535)   # None=自动分配;越界 422(bind(70000) 是 OverflowError 非 OSError)
    cors_enabled: bool = False
    default_status: int = Field(404, ge=100, le=599)
    default_body: str | None = None
    # 透传已移至规则组级(2026-09-13 验收调整):实例只余兜底,"被 mock 的原始接口"是组级概念


class MockInstancePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    port: int | None = Field(None, ge=1, le=65535)   # None=不改;越界 422
    cors_enabled: bool | None = None
    default_status: int | None = Field(None, ge=100, le=599)
    default_body: str | None = None


class MockInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    project_id: int
    name: str
    description: str | None
    port: int
    cors_enabled: bool
    default_status: int
    default_body: str | None
    desired: str
    status: str
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class MockRuleSave(BaseModel):
    group_id: int
    conditions: list[MockCondition] = []
    enabled: bool = True
    response_status: int = Field(200, ge=100, le=599)
    response_headers: dict[str, str] = {}
    response_body: str | None = None
    enable_template: bool = False
    delay_ms: int = Field(0, ge=0)
    timeout_enabled: bool = False
    timeout_seconds: int = Field(30, ge=1, le=3600)


class MockRulePatch(MockRuleSave):
    group_id: int | None = None   # 部分PATCH:允许省略;规则改挂组暂不支持(端点不应用该字段)
    conditions: list[MockCondition] | None = None
    enabled: bool | None = None
    response_status: int | None = Field(None, ge=100, le=599)
    response_headers: dict[str, str] | None = None
    enable_template: bool | None = None   # 部分PATCH语义:省略=不改(否则启停开关会静默重置模板渲染)
    delay_ms: int | None = Field(None, ge=0)
    timeout_enabled: bool | None = None
    timeout_seconds: int | None = Field(None, ge=1, le=3600)


class MockRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    instance_id: int
    group_id: int
    conditions: list
    enabled: bool
    response_status: int
    response_headers: dict
    response_body: str | None
    enable_template: bool
    delay_ms: int
    timeout_enabled: bool
    timeout_seconds: int
    sort_order: int
    updated_at: datetime


class MockRuleGroupSave(BaseModel):
    method: str
    path_template: str
    description: str | None = None
    enabled: bool = True
    passthrough_enabled: bool = False   # 组级透传:组路由命中但组内规则全不中→转发该组上游
    upstream_base_url: str | None = None


class MockRuleGroupPatch(BaseModel):
    method: str | None = None
    path_template: str | None = None
    description: str | None = None
    enabled: bool | None = None
    passthrough_enabled: bool | None = None
    upstream_base_url: str | None = None


class MockRuleGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    instance_id: int
    method: str
    path_template: str
    description: str | None
    enabled: bool
    passthrough_enabled: bool
    upstream_base_url: str | None
    sort_order: int
    rules: list[MockRuleOut] = []
    updated_at: datetime


class MockReorderBody(BaseModel):
    rule_ids: list[int]


class MockGroupReorderBody(BaseModel):
    group_ids: list[int]


class MockHitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    instance_id: int
    rule_id: int | None
    method: str
    path: str
    query: str | None
    matched: bool
    outcome: str
    response_status: int | None
    delay_ms: int
    elapsed_ms: int
    error: str | None
    created_at: datetime


class MockHitDetailOut(MockHitOut):
    request_headers: dict | None
    request_body: str | None
    response_body: str | None
