"""计划6新列往返:thinking_text 可写读,JobOut 透出。"""
from app.database import SessionLocal
from app.models import GenerationJob, Project
from app.schemas import GenerationJobOut


def test_thinking_column_roundtrip():
    db = SessionLocal()
    try:
        project = Project(name="计划6思考列测试项目")
        db.add(project)
        db.flush()
        job = GenerationJob(project_id=project.id, job_type="case_generation", status="completed")
        job.thinking_text = "模型思考摘要:先分析文档结构,再拆功能点…"
        db.add(job)
        db.commit()
        db.expire_all()

        got = db.get(GenerationJob, job.id)
        assert got.thinking_text == "模型思考摘要:先分析文档结构,再拆功能点…"

        out = GenerationJobOut.model_validate(got)
        assert out.thinking_text == "模型思考摘要:先分析文档结构,再拆功能点…"
    finally:
        db.close()
