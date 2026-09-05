from app.database import SessionLocal
from app.models import GenerationJob, Project, StagedCase, Document
from app.schemas import GenerationJobOut


def test_generation_job_and_staged_case_roundtrip():
    db = SessionLocal()
    try:
        project = Project(name="管道项目")
        db.add(project)
        db.flush()
        job = GenerationJob(project_id=project.id, document_id=None, target_module_id=None)
        db.add(job)
        db.flush()
        staged = StagedCase(
            job_id=job.id,
            feature_point_name="账号登录",
            title="正确账号密码登录成功",
            priority="P0",
            precondition="已注册用户",
            remark=None,
            steps=[{"action": "输入账号密码", "expected": "登录成功"}],
        )
        db.add(staged)
        db.commit()

        got = db.get(GenerationJob, job.id)
        assert got.status == "pending"
        assert got.job_type == "case_generation"
        assert got.model is None
        assert got.cost_usd == 0
        assert got.staged is not None
    finally:
        db.close()


def test_generation_job_document_name_property():
    """测试 GenerationJob 的 document_name 只读 property 及 Out 序列化"""
    db = SessionLocal()
    try:
        project = Project(name="文档名测试项目")
        db.add(project)
        db.flush()

        # 有 document 的场景
        document = Document(
            project_id=project.id,
            filename="需求文档.xlsx",
            storage_path="/tmp/fake.xlsx"
        )
        db.add(document)
        db.flush()

        job = GenerationJob(
            project_id=project.id,
            document_id=document.id,
            target_module_id=None
        )
        db.add(job)
        db.commit()

        got = db.get(GenerationJob, job.id)
        assert got.document_name == "需求文档.xlsx"

        # 验证 Out 序列化包含 document_name
        job_out = GenerationJobOut.model_validate(got)
        assert job_out.document_name == "需求文档.xlsx"

        # 无 document 的场景
        job_no_doc = GenerationJob(
            project_id=project.id,
            document_id=None,
            target_module_id=None
        )
        db.add(job_no_doc)
        db.commit()

        got_no_doc = db.get(GenerationJob, job_no_doc.id)
        assert got_no_doc.document_name is None

        # 验证 Out 序列化时 document_name 为 None
        job_out_no_doc = GenerationJobOut.model_validate(got_no_doc)
        assert job_out_no_doc.document_name is None

    finally:
        db.close()
