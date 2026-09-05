from app.database import SessionLocal
from app.models import GenerationJob, Project


def test_artifacts_column_roundtrip():
    db = SessionLocal()
    try:
        project = Project(name="artifacts 测试项目")
        db.add(project)
        db.flush()
        job = GenerationJob(project_id=project.id, job_type="api_generation")
        job.artifacts = [{"path": "src/test/java/T.java", "action": "created"}]
        db.add(job)
        db.commit()
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.artifacts == [{"path": "src/test/java/T.java", "action": "created"}]
        # case_generation 默认 None
        case_job = GenerationJob(project_id=project.id, job_type="case_generation")
        db.add(case_job)
        db.commit()
        assert db.get(GenerationJob, case_job.id).artifacts is None
    finally:
        db.close()
