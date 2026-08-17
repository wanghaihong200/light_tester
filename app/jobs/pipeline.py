"""生成任务管道:asyncio 队列 + 3 worker + 同项目互斥锁。

process_job 是核心处理单元,测试可直接 await 驱动(不经队列)。
AI 调用失败不重抛:任务落 failed + error,SSE 推 error。
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Literal

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
    priority: Literal["P0", "P1", "P2"]  # 枚举在本地校验——端点可能不强制 output_config(schema enum 不可依赖)
    precondition: str | None = None
    remark: str | None = None
    steps: list[StagedStepItem] = Field(default_factory=list)


class StagedFeature(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    cases: list[StagedCaseItem]


class StagedPayload(BaseModel):
    feature_points: list[StagedFeature]


def _strip_code_fence(text: str) -> str:
    """剥离 markdown 代码围栏(```json ... ```)——不强制结构化输出的端点上模型常见输出。"""
    t = text.strip()
    if t.startswith("```"):
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _parse_staged_payload(text: str) -> StagedPayload:
    """解析 AI 输出并归一化后做 pydantic 校验。

    output_config 的服务端 schema 强约束依端点而异(部分兼容端点静默丢弃该参数),
    因此解析层兜底:剥围栏、顶层数组归一化为 {"feature_points": [...]};形状
    仍不符时由 pydantic 校验报错落 job.error。
    """
    data = json.loads(_strip_code_fence(text))
    if isinstance(data, list):
        data = {"feature_points": data}
    return StagedPayload.model_validate(data)


JOBS_QUEUE: asyncio.Queue[int] = asyncio.Queue()
_project_locks: dict[int, asyncio.Lock] = {}

# 事件循环引用,用于跨线程安全地向 asyncio.Queue 投递任务。
# FastAPI 默认用线程池执行 sync def 端点,enqueue_job 会在非 asyncio 线程中调用,
# 直接操作 asyncio.Queue 不安全(依赖 CPython 实现细节)。
_loop: asyncio.AbstractEventLoop | None = None


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    """记录主事件循环,供 enqueue_job 跨线程调用。应在 lifespan 中无条件调用。"""
    global _loop
    _loop = loop


def _lock_for(project_id: int) -> asyncio.Lock:
    return _project_locks.setdefault(project_id, asyncio.Lock())


def enqueue_job(job_id: int) -> None:
    """向队列投递任务。若主事件循环可用则线程安全投递,否则直接操作(兼容测试路径)。"""
    if _loop is not None and _loop.is_running():
        _loop.call_soon_threadsafe(JOBS_QUEUE.put_nowait, job_id)
    else:
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

        # 按 job_type 分发:api_generation 走接口生成 handler,case_generation 走既有逻辑
        if job.job_type == "api_generation":
            # lazy import 避免 pipeline ↔ api_gen 循环导入
            # (api_gen 顶部 from app.jobs.pipeline import _strip_code_fence)
            from app.jobs.api_gen import process_api_job
            await process_api_job(job_id)
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
                await bus.publish(job.id, {"type": "delta", "text": value})
            elif kind == "usage":
                input_tokens, output_tokens = value  # type: ignore[misc]

        # 校验并入库(解析层防御:端点可能不强制结构化输出,见 _parse_staged_payload)
        payload = _parse_staged_payload("".join(chunks))
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
