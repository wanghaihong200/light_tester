# tests/test_job_dispatch.py
import pytest

from app.jobs.pipeline import process_job


def _admin_headers(client, db_session):
    """Task 7 补鉴权:bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。
    原断言语义不变,仅补鉴权头。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


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
def test_create_job_api_generation_requires_git_repo_url(client, db_session):
    """POST /api/projects/{id}/jobs 带 job_type=api_generation 但项目无 git_repo_url→400。"""
    from app.database import SessionLocal
    from app.models import Project, Document, Module
    ah = _admin_headers(client, db_session)
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
            headers=ah,
        )
        assert r.status_code == 400
        assert "git_repo_url" in r.json()["detail"]
    finally:
        db.close()


def test_create_job_with_module_name_creates_module(client, db_session):
    """模块手输文本:项目下无同名顶层模块则新建,job 挂到新模块。"""
    from app.database import SessionLocal
    from app.models import Project, Document, Module, GenerationJob
    ah = _admin_headers(client, db_session)
    db = SessionLocal()
    try:
        proj = Project(name="手输模块项目")
        db.add(proj)
        db.flush()
        doc = Document(project_id=proj.id, filename="需求.md", storage_path="/tmp/fake.md")
        db.add(doc)
        db.commit()
        r = client.post(
            f"/api/projects/{proj.id}/jobs",
            json={"document_id": doc.id, "target_module_name": "手输的新模块", "job_type": "case_generation"},
            headers=ah,
        )
        assert r.status_code == 201
        created = db.query(Module).filter_by(project_id=proj.id, name="手输的新模块").first()
        assert created is not None
        job = db.get(GenerationJob, r.json()["id"])
        assert job.target_module_id == created.id
    finally:
        db.close()


def test_create_job_with_existing_module_name_reuses(client, db_session):
    """模块手输文本与已有顶层模块同名:复用不新建。"""
    from app.database import SessionLocal
    from app.models import Project, Document, Module
    ah = _admin_headers(client, db_session)
    db = SessionLocal()
    try:
        proj = Project(name="复用模块项目")
        db.add(proj)
        db.flush()
        doc = Document(project_id=proj.id, filename="需求.md", storage_path="/tmp/fake.md")
        db.add(doc)
        db.flush()
        mod = Module(project_id=proj.id, name="已有模块", parent_id=None)
        db.add(mod)
        db.commit()
        r = client.post(
            f"/api/projects/{proj.id}/jobs",
            json={"document_id": doc.id, "target_module_name": "已有模块", "job_type": "case_generation"},
            headers=ah,
        )
        assert r.status_code == 201
        assert r.json()["target_module_id"] == mod.id
        assert db.query(Module).filter_by(project_id=proj.id).count() == 1
    finally:
        db.close()


def test_create_job_without_module_ok(client, db_session):
    """模块留空:任务可发起,target_module_id 为 NULL。"""
    from app.database import SessionLocal
    from app.models import Project, Document
    ah = _admin_headers(client, db_session)
    db = SessionLocal()
    try:
        proj = Project(name="空模块项目")
        db.add(proj)
        db.flush()
        doc = Document(project_id=proj.id, filename="需求.md", storage_path="/tmp/fake.md")
        db.add(doc)
        db.commit()
        r = client.post(
            f"/api/projects/{proj.id}/jobs",
            json={"document_id": doc.id, "job_type": "case_generation"},
            headers=ah,
        )
        assert r.status_code == 201
        assert r.json()["target_module_id"] is None
    finally:
        db.close()
