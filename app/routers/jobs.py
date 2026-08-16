import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.jobs.bus import bus
from app.jobs.pipeline import enqueue_job
from app.models import Document, GenerationJob, Module, Project
from app.schemas import GenerationJobOut

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

    async def event_stream():
        try:
            yield _sse({"type": "status", "status": snapshot_status})
            if snapshot_status in ("completed", "failed"):
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
    target_module_id: int


@router.post("/projects/{project_id}/jobs", response_model=GenerationJobOut, status_code=201)
def create_job(project_id: int, payload: JobCreate, db: Session = Depends(get_db)):
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    doc = db.get(Document, payload.document_id)
    if doc is None or doc.project_id != project_id:
        raise HTTPException(400, "invalid document_id")
    module = db.get(Module, payload.target_module_id)
    if module is None or module.project_id != project_id:
        raise HTTPException(400, "invalid target_module_id")
    job = GenerationJob(
        project_id=project_id,
        document_id=payload.document_id,
        target_module_id=payload.target_module_id,
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
