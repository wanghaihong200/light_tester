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
