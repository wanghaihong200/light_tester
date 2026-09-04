"""Task 11:归属列 created_by/updated_by。

口径:
- create 端点写 created_by=current.id,不写 updated_by(jobs 例外:发起时两列同值写入);
- update 端点写 updated_by=current.id;
- worker 翻转 job 状态不经用户,不碰两列。
"""
import pytest


def _admin_headers(client, db_session):
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    """建用户+分配项目+登录,返回 Authorization 头(与 test_project_isolation 同型)。"""
    u = make_user(db_session, name)
    from app.models import Project, ProjectMember

    if project_ids is None:
        pids: list[int] = []
    elif isinstance(project_ids, (list, tuple)):
        pids = list(project_ids)
    else:
        pids = [project_ids]
    for pid in pids:
        if db_session.get(Project, pid) is None:
            db_session.add(Project(name=f"p-{pid}"))
            db_session.flush()
        db_session.add(ProjectMember(project_id=pid, user_id=u.id, role=role))
    db_session.commit()
    r = client.post("/api/auth/login", json={"username": name, "password": f"pw-{name}"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_create_stamps_created_by(client, db_session, make_user):
    from app.bootstrap import ensure_bootstrap_admin
    from app.models import Project, User

    ensure_bootstrap_admin(db_session)
    h = _auth(client, db_session, make_user, "maker")
    r = client.post("/api/projects", json={"name": "attr"}, headers=h)
    assert r.status_code == 201
    u = db_session.query(User).filter_by(username="maker").first()
    p = db_session.query(Project).filter_by(name="attr").first()
    assert p.created_by == u.id and p.updated_by is None


def test_update_project_stamps_updated_by(client, db_session, make_user):
    """admin 建项目(created_by=admin),成员编辑(updated_by=成员,created_by 不变)。"""
    from app.models import Project, User

    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "归属更新"}, headers=ah).json()["id"]
    eh = _auth(client, db_session, make_user, "editor01", project_ids=[pid], role="editor")
    r = client.put(f"/api/projects/{pid}", json={"description": "改描述"}, headers=eh)
    assert r.status_code == 200
    admin = db_session.query(User).filter_by(username="admin").first()
    editor = db_session.query(User).filter_by(username="editor01").first()
    p = db_session.get(Project, pid)
    assert p.created_by == admin.id
    assert p.updated_by == editor.id


def test_upload_document_stamps_created_by(client, db_session, make_user):
    from app.models import Document, User

    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "文档归属"}, headers=ah).json()["id"]
    eh = _auth(client, db_session, make_user, "uploader", project_ids=[pid], role="editor")
    r = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("需求.md", "# 需求".encode("utf-8"), "text/markdown")},
        headers=eh,
    )
    assert r.status_code == 201
    u = db_session.query(User).filter_by(username="uploader").first()
    d = db_session.query(Document).filter_by(project_id=pid).first()
    assert d.created_by == u.id and d.updated_by is None  # 文档无用户侧更新路径


def test_ui_script_create_and_update_stamps(client, db_session, make_user):
    from app.models import UiScript, User

    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "脚本归属"}, headers=ah).json()["id"]
    eh = _auth(client, db_session, make_user, "scripter", project_ids=[pid], role="editor")
    body = {"name": "登录脚本", "script": {"version": 1, "steps": []}}
    r = client.post(f"/api/projects/{pid}/ui-scripts", json=body, headers=eh)
    assert r.status_code == 201
    sid = r.json()["id"]
    u = db_session.query(User).filter_by(username="scripter").first()
    row = db_session.get(UiScript, sid)
    assert row.created_by == u.id and row.updated_by is None

    assert client.put(f"/api/ui-scripts/{sid}", json=body, headers=eh).status_code == 200
    # db_session 有身份映射缓存(expire_on_commit=False)+ REPEATABLE READ 快照:
    # 先回滚结束旧快照事务,再显式过期缓存实例,否则 get 会拿到端点更新前的旧值
    db_session.rollback()
    db_session.expire_all()
    row = db_session.get(UiScript, sid)
    assert row.created_by == u.id and row.updated_by == u.id


async def test_job_stamps_both_and_worker_flip_keeps_them(client, db_session, make_user, monkeypatch):
    """发起时 created_by 与 updated_by 同值写入;worker 翻状态不碰两列。"""
    import app.jobs.pipeline as pl
    import app.routers.jobs as jobs_router
    from app.models import GenerationJob, User

    monkeypatch.setattr(jobs_router, "enqueue_job", lambda job_id: None)  # 阻断后台线程,改由本测试驱动

    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "任务归属"}, headers=ah).json()["id"]
    doc = client.post(
        f"/api/projects/{pid}/documents",
        files={"file": ("需求.md", "# 需求".encode("utf-8"), "text/markdown")},
        headers=ah,
    ).json()
    mod = client.post(f"/api/projects/{pid}/modules", json={"name": "归属模块"}, headers=ah).json()
    eh = _auth(client, db_session, make_user, "starter", project_ids=[pid], role="editor")
    # 带上 target_module_id:缺省会触发 pipeline 里 db.get(Module, None) 的 SAWarning(非本基线的警告)
    r = client.post(f"/api/projects/{pid}/jobs", json={"document_id": doc["id"], "target_module_id": mod["id"]}, headers=eh)
    assert r.status_code == 201
    jid = r.json()["id"]
    u = db_session.query(User).filter_by(username="starter").first()
    job = db_session.get(GenerationJob, jid)
    assert job.created_by == u.id and job.updated_by == u.id

    async def boom(*args, **kwargs):
        raise RuntimeError("api down")
        yield  # pragma: no cover

    monkeypatch.setattr(pl, "stream_skill_generation", boom)
    await pl.process_job(jid)  # worker 翻转状态
    # 同前:回滚结束旧快照 + 过期缓存实例,才能读到 worker 已提交的最新状态
    db_session.rollback()
    db_session.expire_all()
    job = db_session.get(GenerationJob, jid)
    assert job.status == "failed" and "api down" in (job.error or "")
    assert job.created_by == u.id and job.updated_by == u.id  # 两列未被 worker 改动
