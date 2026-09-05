"""计划7:补充提示词持久化 + 过程记录列/SSE 快照透出。"""
import json

from app.database import SessionLocal
from app.models import GenerationJob, Project


def _admin_headers(client, db_session):
    """Task 7 补鉴权:bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。
    原断言语义不变,仅补鉴权头。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def test_create_job_persists_user_prompt(client, db_session):
    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "补充提示词项目"}, headers=ah).json()["id"]
    doc = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("r.md", "# 需求".encode("utf-8"), "text/markdown")},
        headers=ah,
    ).json()
    resp = client.post(f"/api/projects/{pid}/jobs", json={
        "document_id": doc["id"], "user_prompt": "只生成登录功能点,优先异常场景",
    }, headers=ah)
    assert resp.status_code == 201
    assert resp.json()["user_prompt"] == "只生成登录功能点,优先异常场景"
    detail = client.get(f"/api/jobs/{resp.json()['id']}", headers=ah).json()
    assert detail["user_prompt"] == "只生成登录功能点,优先异常场景"


def test_user_prompt_optional_and_blank_normalized(client, db_session):
    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "空补充项目"}, headers=ah).json()["id"]
    doc = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("r.md", "# 需求".encode("utf-8"), "text/markdown")},
        headers=ah,
    ).json()
    assert client.post(f"/api/projects/{pid}/jobs", json={"document_id": doc["id"]}, headers=ah).json()["user_prompt"] is None
    blank = client.post(f"/api/projects/{pid}/jobs", json={"document_id": doc["id"], "user_prompt": "   "}, headers=ah).json()
    assert blank["user_prompt"] is None


def test_terminal_snapshot_includes_tool_trace(client, db_session):
    ah = _admin_headers(client, db_session)
    db = SessionLocal()
    try:
        p = Project(name="过程记录快照项目")
        db.add(p)
        db.flush()
        job = GenerationJob(
            project_id=p.id, document_id=None, target_module_id=None,
            status="completed", output_text="产物", thinking_text="思考",
            tool_trace="Read SKILL.md\nBash mvn -q test-compile\n",
        )
        db.add(job)
        db.commit()
        jid = job.id
    finally:
        db.close()
    with client.stream("GET", f"/api/jobs/{jid}/events", headers=ah) as r:
        lines = [ln for ln in r.iter_lines() if ln.strip()]
    snap = json.loads(lines[1][len("data: "):])
    assert snap["tool_trace"] == "Read SKILL.md\nBash mvn -q test-compile\n"
