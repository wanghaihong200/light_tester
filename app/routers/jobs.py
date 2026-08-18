import asyncio
import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.jobs.bus import bus
from app.jobs.pipeline import enqueue_job
from app.models import Case, Document, FeaturePoint, GenerationJob, Module, Project, Step, StagedCase
from app.schemas import GenerationJobOut, StagedCaseOut

router = APIRouter(prefix="/api", tags=["jobs"])


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: int, db: Session = Depends(get_db)):
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    queue = bus.subscribe(job_id)
    snapshot_status = job.status
    # ORM 陷阱:Depends 的 db 在生成器执行时可能已关闭,先取值存局部变量
    _job_status = job.status
    _job_error = job.error
    _job_output_text = job.output_text
    _job_thinking_text = job.thinking_text
    _job_input_tokens = job.input_tokens
    _job_output_tokens = job.output_tokens
    _files_count = len(job.artifacts or [])
    _staged_count = db.query(StagedCase).filter(StagedCase.job_id == job_id, StagedCase.is_deleted.is_(False)).count()

    async def event_stream():
        try:
            yield _sse({"type": "status", "status": snapshot_status})
            if snapshot_status in ("completed", "failed"):
                yield _sse({
                    "type": "snapshot",
                    "status": _job_status,
                    "error": _job_error,
                    "output_text": _job_output_text,
                    "thinking_text": _job_thinking_text,
                    "input_tokens": _job_input_tokens,
                    "output_tokens": _job_output_tokens,
                    "files_count": _files_count,
                    "staged_count": _staged_count,
                })
                return
            while True:
                event = await queue.get()
                yield _sse(event)
                if event.get("type") in ("done", "error"):
                    return
        finally:
            bus.unsubscribe(job_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class JobCreate(BaseModel):
    document_id: int
    # 模块三选一:id(下拉选中)/ name(手输文本,项目下同名顶层模块复用,无则新建)/ 均空(不挂模块)
    target_module_id: int | None = None
    target_module_name: str | None = None
    job_type: Literal["case_generation", "api_generation"] = "case_generation"


def _resolve_module_id(db: Session, project_id: int, payload: JobCreate) -> int | None:
    """解析目标模块:id 优先校验沿用;仅手输名字时复用/新建同名顶层模块;均空返回 None。"""
    if payload.target_module_id is not None:
        module = db.get(Module, payload.target_module_id)
        if module is None or module.project_id != project_id:
            raise HTTPException(400, "invalid target_module_id")
        return payload.target_module_id
    name = (payload.target_module_name or "").strip()
    if not name:
        return None
    existing = (
        db.query(Module)
        .filter(Module.project_id == project_id, Module.name == name, Module.parent_id.is_(None))
        .first()
    )
    if existing is not None:
        return existing.id
    created = Module(project_id=project_id, name=name, parent_id=None)
    db.add(created)
    db.flush()
    return created.id


@router.post("/projects/{project_id}/jobs", response_model=GenerationJobOut, status_code=201)
def create_job(project_id: int, payload: JobCreate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    doc = db.get(Document, payload.document_id)
    if doc is None or doc.project_id != project_id:
        raise HTTPException(400, "invalid document_id")
    module_id = _resolve_module_id(db, project_id, payload)
    # api_generation 必须有有效 http(s) git_repo_url(case_generation 不要求)
    if payload.job_type == "api_generation":
        from app.git_service import GitError, validate_repo_url
        try:
            validate_repo_url(project.git_repo_url or "")
        except GitError:
            raise HTTPException(400, "项目未配置有效的 git_repo_url")
    job = GenerationJob(
        project_id=project_id,
        document_id=payload.document_id,
        target_module_id=module_id,
        job_type=payload.job_type,
        model=settings.ai_model,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    enqueue_job(job.id)
    return job


@router.get("/projects/{project_id}/jobs", response_model=list[GenerationJobOut])
def list_jobs(project_id: int, db: Session = Depends(get_db)):
    return (
        db.query(GenerationJob)
        .filter(GenerationJob.project_id == project_id)
        .order_by(GenerationJob.id.desc())
        .all()
    )


@router.get("/jobs/{job_id}", response_model=GenerationJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job


# ── 暂存区三端点 ──────────────────────────────────────────────


class StagingAccept(BaseModel):
    ids: list[int]


@router.get("/jobs/{job_id}/staging")
def staging_list(job_id: int, db: Session = Depends(get_db)):
    """暂存区分组列表:按功能点名分组,组内按 id 升序,组按首次出现序"""
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    rows = (
        db.query(StagedCase)
        .filter(StagedCase.job_id == job_id)
        .order_by(StagedCase.id)
        .all()
    )
    groups: list[dict] = []
    order_map: dict[str, int] = {}  # 功能点名 → 组序号
    for row in rows:
        name = row.feature_point_name
        if name not in order_map:
            order_map[name] = len(groups)
            groups.append({"feature_point_name": name, "cases": []})
        groups[order_map[name]]["cases"].append(StagedCaseOut.model_validate(row).model_dump())
    return {"job_id": job_id, "groups": groups}


@router.post("/jobs/{job_id}/staging/accept")
def staging_accept(job_id: int, payload: StagingAccept, db: Session = Depends(get_db)):
    """勾选转正:找或建功能点,插 Case+Steps,删暂存行;全部完成后一次 commit"""
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job.status != "completed":
        raise HTTPException(400, "job not completed")

    # 校验 ids 去重后是否全部命中
    unique_ids = list(dict.fromkeys(payload.ids))
    matched = (
        db.query(StagedCase)
        .filter(StagedCase.job_id == job_id, StagedCase.id.in_(unique_ids))
        .order_by(StagedCase.id)
        .all()
    )
    if len(matched) != len(unique_ids):
        raise HTTPException(400, "部分 id 不属于该 job 或已不存在")

    feature_point_ids: dict[str, int] = {}
    fp_sort_cache: dict[str, int] = {}  # 功能点名 → 当前 sort_order
    accepted = 0

    for staged in matched:
        fp_name = staged.feature_point_name
        # 找或建功能点(名字精确匹配)
        fp = (
            db.query(FeaturePoint)
            .filter_by(module_id=job.target_module_id, name=fp_name)
            .first()
        )
        if fp is None:
            fp = FeaturePoint(module_id=job.target_module_id, name=fp_name)
            db.add(fp)
            db.flush()
        feature_point_ids[fp_name] = fp.id

        # sort_order 顺延
        if fp_name not in fp_sort_cache:
            max_so = (
                db.query(func.max(Case.sort_order))
                .filter(Case.feature_point_id == fp.id)
                .scalar()
            )
            fp_sort_cache[fp_name] = (max_so or 0) + 1
        else:
            fp_sort_cache[fp_name] += 1

        # 插 Case
        case = Case(
            feature_point_id=fp.id,
            title=staged.title,
            priority=staged.priority,
            precondition=staged.precondition,
            remark=staged.remark,
            sort_order=fp_sort_cache[fp_name],
        )
        db.add(case)
        db.flush()

        # 插 Steps
        for idx, step_data in enumerate(staged.steps, start=1):
            db.add(Step(
                case_id=case.id,
                step_no=idx,
                action=step_data["action"],
                expected=step_data["expected"],
            ))

        # 删除暂存行
        db.delete(staged)
        accepted += 1

    db.commit()
    return {"accepted": accepted, "feature_point_ids": feature_point_ids}


@router.delete("/staged/{staged_id}", status_code=204)
def staging_reject(staged_id: int, db: Session = Depends(get_db)):
    """拒绝:物理删除暂存行"""
    staged = db.get(StagedCase, staged_id)
    if staged is None:
        raise HTTPException(404, "staged case not found")
    db.delete(staged)
    db.commit()
