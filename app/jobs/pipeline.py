"""生成任务管道:asyncio 队列 + 3 worker + 同项目互斥锁。

process_job 是核心处理单元,测试可直接 await 驱动(不经队列)。
AI 调用失败不重抛:任务落 failed + error,SSE 推 error。
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.ai.engine import CASE_JSON_SCHEMA, SKILL_CASE, stream_skill_generation
from app.ai.prompts import build_user_prompt
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


STREAM_FLUSH_THRESHOLD = 4096


def flush_output_text(db: Session, job_id: int, buf: list[str]) -> None:
    """把缓冲的流文本增量拼进 generation_jobs.output_text(SQL 侧 CONCAT,不做读改写)。"""
    _append_column(db, job_id, buf, "output_text")


def flush_thinking_text(db: Session, job_id: int, buf: list[str]) -> None:
    """思考摘要增量拼接,与 output_text 同构(计划6)。"""
    _append_column(db, job_id, buf, "thinking_text")


TOOL_TRACE_FLUSH_LINES = 32


def flush_tool_trace(db: Session, job_id: int, buf: list[str]) -> None:
    """过程记录增量拼接(按行累积,与 output_text/thinking_text 同构,计划7)。"""
    _append_column(db, job_id, buf, "tool_trace")


def _append_column(db: Session, job_id: int, buf: list[str], column: str) -> None:
    if not buf:
        return
    chunk = "".join(buf)
    buf.clear()
    db.execute(
        sql_text(f"UPDATE generation_jobs SET {column} = CONCAT(COALESCE({column}, ''), :c) WHERE id = :id"),
        {"c": chunk, "id": job_id},
    )
    db.commit()


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

        stream_buf: list[str] = []
        thinking_buf: list[str] = []
        tool_buf: list[str] = []

        # 按 job_type 分发:api_generation 走接口生成 handler,case_generation 走既有逻辑
        if job.job_type == "api_generation":
            # lazy import 避免 pipeline ↔ api_gen 循环导入
            # (api_gen 顶部 from app.jobs.pipeline import _strip_code_fence)
            from app.jobs.api_gen import process_api_job
            await process_api_job(job_id)
            return

        # 标记运行中
        job.status = "running"
        job.started_at = datetime.now()
        job.model = settings.ai_model
        db.commit()
        await bus.publish(job.id, {"type": "status", "status": "running"})

        # 读取文档内容
        doc = job.document
        module = db.get(Module, job.target_module_id)
        module_name = module.name if module else "(未指定)"
        content = Path(doc.storage_path).read_text(encoding="utf-8")

        # AI 流式生成
        chunks: list[str] = []
        result_payload: dict | None = None
        async for kind, value in stream_skill_generation(
            prompt=build_user_prompt(job.project.name, module_name, content, job.user_prompt),
            skill_name=SKILL_CASE,
            output_schema=CASE_JSON_SCHEMA,
        ):
            if kind == "thinking":
                thinking_buf.append(value)
                await bus.publish(job.id, {"type": "thinking_delta", "text": value})
                if sum(len(s) for s in thinking_buf) >= STREAM_FLUSH_THRESHOLD:
                    flush_thinking_text(db, job.id, thinking_buf)
            elif kind == "delta":
                chunks.append(value)
                stream_buf.append(value)
                await bus.publish(job.id, {"type": "delta", "text": value})
                if sum(len(s) for s in stream_buf) >= STREAM_FLUSH_THRESHOLD:
                    flush_output_text(db, job.id, stream_buf)
            elif kind == "tool":
                tool_buf.append(value + "\n")
                await bus.publish(job.id, {"type": "tool", "text": value + "\n"})
                if len(tool_buf) >= TOOL_TRACE_FLUSH_LINES:
                    flush_tool_trace(db, job.id, tool_buf)
            elif kind == "usage":
                in_t, out_t, cost = value
                # A3 语义延续:usage 到达即累计落库;费用来自 SDK total_cost_usd(整树估算)
                job.input_tokens = (job.input_tokens or 0) + in_t
                job.output_tokens = (job.output_tokens or 0) + out_t
                job.cost_usd = (job.cost_usd or 0.0) + cost
                db.commit()
            elif kind == "result":
                result_payload = value

        # 校验并入库:result 优先(SDK 结构化输出),叙述文本解析兜底(防御旧姿态延续)
        if result_payload is not None:
            payload = StagedPayload.model_validate(result_payload)
            stream_buf.append("\n\n===== 产物 JSON =====\n\n" + json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n")
        else:
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

        # 完成
        flush_output_text(db, job.id, stream_buf)
        flush_thinking_text(db, job.id, thinking_buf)
        flush_tool_trace(db, job.id, tool_buf)
        job.finished_at = datetime.now()
        job.status = "completed"
        db.commit()
        await bus.publish(job.id, {"type": "done", "staged_count": staged_count})

    except Exception as exc:
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job is not None:
            job.status = "failed"
            job.error = str(exc)[:2000]
            job.finished_at = datetime.now()
            flush_output_text(db, job.id, stream_buf)
            flush_thinking_text(db, job.id, thinking_buf)
            flush_tool_trace(db, job.id, tool_buf)
            db.commit()
        await bus.publish(job_id, {"type": "error", "message": str(exc)[:500]})

    finally:
        db.close()
