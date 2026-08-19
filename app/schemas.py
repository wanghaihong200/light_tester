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
