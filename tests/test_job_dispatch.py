# tests/test_job_dispatch.py
import pytest

from app.jobs.pipeline import process_job


@pytest.mark.asyncio
async def test_process_job_dispatches_api_generation(monkeypatch):
    """job_type=api_generation 时调用 process_api_job,不走 case 分支。"""
    called = {}

    async def fake_api(job_id):
        called["api"] = job_id

    # Issue A: monkeypatch app.jobs.api_gen.process_api_job(非 app.jobs.pipeline)
    # process_job 内 lazy import `from app.jobs.api_gen import process_api_job`,
    # 调用时从 app.jobs.api_gen 模块取当前属性,故 patch 该模块属性生效。
    monkeypatch.setattr("app.jobs.api_gen.process_api_job", fake_api)
    # 造一个 api_generation job 并驱动 process_job
    from app.database import SessionLocal
    from app.models import GenerationJob, Project
    db = SessionLocal()
    try:
        proj = Project(name="dispatch 测试")
        db.add(proj)
        db.flush()
        job = GenerationJob(project_id=proj.id, job_type="api_generation")
        db.add(job)
        db.commit()
        await process_job(job.id)
        assert called.get("api") == job.id
    finally:
        db.close()


# Issue D: 用 SessionLocal() 直接操作(无 db_session fixture)
# Issue E: 创建有效 Document + Module,使校验走到 git_repo_url 而非 document_id
def test_create_job_api_generation_requires_git_repo_url(client):
    """POST /api/projects/{id}/jobs 带 job_type=api_generation 但项目无 git_repo_url→400。"""
    from app.database import SessionLocal
    from app.models import Project, Document, Module
    db = SessionLocal()
    try:
        proj = Project(name="no-git 项目")
        db.add(proj)
        db.flush()
        doc = Document(project_id=proj.id, filename="需求.md", storage_path="/tmp/fake.md")
        db.add(doc)
        db.flush()
        mod = Module(project_id=proj.id, name="m")
        db.add(mod)
        db.commit()
        r = client.post(
            f"/api/projects/{proj.id}/jobs",
            json={
                "document_id": doc.id,
                "target_module_id": mod.id,
                "job_type": "api_generation",
            },
        )
        assert r.status_code == 400
        assert "git_repo_url" in r.json()["detail"]
    finally:
        db.close()
