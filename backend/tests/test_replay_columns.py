"""计划5新列往返:output_text / started_at / finished_at 可写读,JobOut 透出。"""
from datetime import datetime

from app.database import SessionLocal
from app.models import GenerationJob, Project
from app.schemas import GenerationJobOut


def test_replay_columns_roundtrip():
    db = SessionLocal()
    try:
        project = Project(name="计划5新列测试项目")
        db.add(project)
        db.flush()
        job = GenerationJob(project_id=project.id, job_type="case_generation", status="completed")
        job.output_text = "AI 流式输出全文…"
        job.started_at = datetime(2026, 8, 18, 10, 0, 0)
        job.finished_at = datetime(2026, 8, 18, 10, 2, 30)
        db.add(job)
        db.commit()
        db.expire_all()

        got = db.get(GenerationJob, job.id)
        assert got.output_text == "AI 流式输出全文…"
        assert got.started_at is not None and got.started_at.hour == 10
        assert got.finished_at is not None and got.finished_at.second == 30

        out = GenerationJobOut.model_validate(got)
        assert out.output_text == "AI 流式输出全文…"
        assert out.started_at is not None and out.finished_at is not None
    finally:
        db.close()
