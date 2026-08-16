import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.jobs.bus import bus
from app.models import GenerationJob

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
