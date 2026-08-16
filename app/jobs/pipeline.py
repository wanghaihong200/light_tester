"""生成任务管道:asyncio 队列 + 3 worker + 同项目互斥锁。

process_job 是核心处理单元,测试可直接 await 驱动(不经队列)。
AI 调用失败不重抛:任务落 failed + error,SSE 推 error。
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.client import estimate_cost, stream_case_generation
from app.config import settings
from app.database import SessionLocal
from app.jobs.bus import bus
from app.models import GenerationJob, Module, StagedCase


class StagedStepItem(BaseModel):
    action: str = Field(min_length=1)
    expected: str = Field(min_length=1)


class StagedCaseItem(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    priority: str  # P0/P1/P2,由 schema enum 约束
    precondition: str | None = None
    remark: str | None = None
    steps: list[StagedStepItem] = Field(default_factory=list)


class StagedFeature(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    cases: list[StagedCaseItem]


class StagedPayload(BaseModel):
    feature_points: list[StagedFeature]


JOBS_QUEUE: asyncio.Queue[int] = asyncio.Queue()
_project_locks: dict[int, asyncio.Lock] = {}


def _lock_for(project_id: int) -> asyncio.Lock:
    return _project_locks.setdefault(project_id, asyncio.Lock())


def enqueue_job(job_id: int) -> None:
    JOBS_QUEUE.put_nowait(job_id)


async def worker_loop() -> None:
    while True:
        job_id = await JOBS_QUEUE.get()
        db = SessionLocal()
        try:
            job = db.get(GenerationJob, job_id)
            if job is None:
                continue
            async with _lock_for(job.project_id):
                await process_job(job_id)
        finally:
            db.close()


async def process_job(job_id: int) -> None:
    """核心处理单元:读文档 → AI 流式生成 → 校验 → 落库 → 推事件。"""
    db: Session = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return

        # 标记运行中
        job.status = "running"
        job.model = settings.ai_model
        db.commit()
        await bus.publish(job.id, {"type": "status", "status": "running"})

        # 读取文档内容
        doc = job.document
        module = db.get(Module, job.target_module_id)
        content = Path(doc.storage_path).read_text(encoding="utf-8")

        # AI 流式生成
        chunks: list[str] = []
        input_tokens = 0
        output_tokens = 0
        async for kind, value in stream_case_generation(job.project.name, module.name, content):
            if kind == "delta":
                chunks.append(value)
                await bus.publish(job.id, {"type": "delta"})
            elif kind == "usage":
                input_tokens, output_tokens = value  # type: ignore[misc]

        # 校验并入库
        payload = StagedPayload.model_validate(json.loads("".join(chunks)))
        staged_count = 0
        for fp in payload.feature_points:
            for case in fp.cases:
                db.add(StagedCase(
                    job_id=job.id,
                    feature_point_name=fp.name,
                    title=case.title,
                    priority=case.priority,
                    precondition=case.precondition,
                    remark=case.remark,
                    steps=[s.model_dump() for s in case.steps],
                ))
                staged_count += 1

        # tokens / 费用
        job.input_tokens = input_tokens
        job.output_tokens = output_tokens
        job.cost_usd = estimate_cost(job.model, input_tokens, output_tokens)
        db.commit()

        # 完成
        job.status = "completed"
        db.commit()
        await bus.publish(job.id, {"type": "done", "staged_count": staged_count})

    except Exception as exc:
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)[:2000]
            db.commit()
        await bus.publish(job_id, {"type": "error", "message": str(exc)[:500]})

    finally:
        db.close()
