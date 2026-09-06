"""Task 7:jobs/repo 路由项目级隔离测试。
发起生成/删除/详情/SSE 事件 = editor+(发起生成花钱,viewer 禁——共识硬点);
repo 读端点(文件/分支)= viewer,push/sync 写外部系统 = editor。
_auth helper 从 tests/test_project_isolation.py(Task 5 修正版)复制为同型 helper。
注:简报样例的 POST /api/jobs、GET /api/jobs 在本后端不存在,真实路由为
POST/GET /api/projects/{project_id}/jobs(project_id 在路径上,body 契约以 jobs.JobCreate 为准),
断言语义不变:viewer 发起 403;非成员项目的 job 不可见(404)。"""

import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _clean_automation_repos():
    """计划 11 Task 2(方案 B,用户批准):repo 端点改为按 AutomationRepo 行解析。
    conftest._TABLES 未含 automation_repos,projects 被 TRUNCATE 复位自增后 id 复用,
    残留行会串项目(与 tests/test_automation_repo.py 同款清理)。"""
    yield
    from app.database import SessionLocal

    session = SessionLocal()
    try:
        session.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        session.execute(text("TRUNCATE TABLE automation_repos"))
        session.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        session.commit()
    finally:
        session.close()


def _seed_api_repo(db, project_id, repo_url, repo_token=None):
    """给已存在的项目补种 kind=api 仓行(Task 3 写透落地前,API 建项目不产生该行)。"""
    from app.models import AutomationRepo

    row = AutomationRepo(project_id=project_id, kind="api", repo_url=repo_url, repo_token=repo_token)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _admin_headers(client, db_session):
    """bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    """建用户+分配项目+登录,返回 Authorization 头。(复制自 Task 5 修正版:归一化空元组缺省)"""
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


def _project(client, ah, name):
    return client.post("/api/projects", json={"name": name}, headers=ah).json()["id"]


def _document(client, ah, pid, name="需求.md"):
    return client.post(
        f"/api/projects/{pid}/documents",
        files={"file": (name, "# 需求".encode("utf-8"), "text/markdown")},
        headers=ah,
    ).json()


def _seed_job(db_session, project_id, status="completed"):
    """admin 直接插一条 job 行(绕过发起闸门),返回 job id。"""
    from app.models import GenerationJob

    job = GenerationJob(project_id=project_id, job_type="case_generation", status=status)
    db_session.add(job)
    db_session.commit()
    return job.id


def test_viewer_cannot_create_job(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "j1")
    _document(client, ah, pid)
    vh = _auth(client, db_session, make_user, "vjob", project_ids=[pid], role="viewer")
    doc_id = client.get(f"/api/projects/{pid}/documents", headers=vh).json()[0]["id"]
    r = client.post(
        f"/api/projects/{pid}/jobs",
        json={"document_id": doc_id, "job_type": "case_generation"},
        headers=vh,
    )
    assert r.status_code == 403  # viewer 花不了 API 额度


def test_editor_can_create_job(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "j2")
    _document(client, ah, pid)
    eh = _auth(client, db_session, make_user, "ejob", project_ids=[pid], role="editor")
    doc_id = client.get(f"/api/projects/{pid}/documents", headers=eh).json()[0]["id"]
    r = client.post(
        f"/api/projects/{pid}/jobs",
        json={"document_id": doc_id, "job_type": "case_generation"},
        headers=eh,
    )
    assert r.status_code == 201
    assert r.json()["status"] == "pending"


def test_jobs_list_filtered(client, db_session, make_user):
    # admin 建两项目;user 只在 p2;p1 的 job(Admin 直插)对 user 不可见
    ah = _admin_headers(client, db_session)
    p1 = _project(client, ah, "jl1")
    p2 = _project(client, ah, "jl2")
    jid = _seed_job(db_session, p1)
    uh = _auth(client, db_session, make_user, "jobseer", project_ids=[p2], role="viewer")
    # 非成员列 p1 的 jobs:404(不可见),绝不吐出 p1 的 job
    assert client.get(f"/api/projects/{p1}/jobs", headers=uh).status_code == 404
    assert client.get(f"/api/projects/{p1}/jobs/{jid}", headers=uh).status_code == 404
    # 成员列自己项目的 jobs:200,且只含自己项目
    body = client.get(f"/api/projects/{p2}/jobs", headers=uh).json()
    assert body == []
    # admin 直通:p1 的 job 可见
    ids = [j["id"] for j in client.get(f"/api/projects/{p1}/jobs", headers=ah).json()]
    assert jid in ids


def test_job_detail_gate(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "jd")
    jid = _seed_job(db_session, pid)
    vh = _auth(client, db_session, make_user, "jviewer", project_ids=[pid], role="viewer")
    # 不存在与不可见同 404(不泄漏存在性);成员但角色不足 → 403
    assert client.get("/api/jobs/999999", headers=vh).status_code == 404
    assert client.get(f"/api/jobs/{jid}", headers=vh).status_code == 403
    assert client.get(f"/api/jobs/{jid}", headers=ah).status_code == 200


def test_sse_events_gate(client, db_session, make_user):
    """Task 4 评审遗留指针:SSE 端点在 get_current_user_sse 之上补项目 editor 闸。"""
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "je")
    jid = _seed_job(db_session, pid)
    vh = _auth(client, db_session, make_user, "jeviewer", project_ids=[pid], role="viewer")
    oh = _auth(client, db_session, make_user, "jeoutsider", project_ids=[], role="viewer")
    assert client.get("/api/jobs/999999/events", headers=vh).status_code == 404  # 不存在
    assert client.get(f"/api/jobs/{jid}/events", headers=oh).status_code == 404  # 非成员不可见
    assert client.get(f"/api/jobs/{jid}/events", headers=vh).status_code == 403  # viewer 禁
    with client.stream("GET", f"/api/jobs/{jid}/events", headers=ah) as r:
        assert r.status_code == 200  # admin 直通
        assert r.headers["content-type"].startswith("text/event-stream")


def test_staging_endpoints_gate(client, db_session, make_user):
    """暂存区三端点挂 job → 闸 job.project_id:viewer 403 / 非成员与不存在 404。"""
    from app.models import StagedCase

    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "js")
    jid = _seed_job(db_session, pid)
    s = StagedCase(job_id=jid, feature_point_name="登录", title="t", priority="P0", steps=[])
    db_session.add(s)
    db_session.commit()
    sid = s.id
    vh = _auth(client, db_session, make_user, "jsviewer", project_ids=[pid], role="viewer")
    oh = _auth(client, db_session, make_user, "jsoutsider", project_ids=[], role="editor")
    assert client.get(f"/api/jobs/{jid}/staging", headers=vh).status_code == 403
    assert client.post(f"/api/jobs/{jid}/staging/accept", json={"ids": [sid]}, headers=vh).status_code == 403
    assert client.delete(f"/api/staged/{sid}", headers=vh).status_code == 403
    # 非成员 / 不存在 → 404
    assert client.get(f"/api/jobs/{jid}/staging", headers=oh).status_code == 404
    assert client.get("/api/jobs/999999/staging", headers=ah).status_code == 404
    assert client.delete("/api/staged/999999", headers=ah).status_code == 404
    # admin 直通可读
    assert client.get(f"/api/jobs/{jid}/staging", headers=ah).status_code == 200


def test_repo_viewer_reads_editor_writes(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = _project(client, ah, "jr")
    # Task 2(方案 B):端点按 AutomationRepo 行解析;补种 api 行使 files 走「行存在但未同步」分支
    _seed_api_repo(db_session, pid, "file:///tmp/jr-none", None)
    vh = _auth(client, db_session, make_user, "jrviewer", project_ids=[pid], role="viewer")
    oh = _auth(client, db_session, make_user, "jroutsider", project_ids=[], role="viewer")
    # 读端点 viewer 可读(未同步 → needs_sync)
    r = client.get(f"/api/projects/{pid}/repo/files", headers=vh)
    assert r.status_code == 200 and r.json() == {"needs_sync": True}
    # 写外部系统端点 viewer → 403
    assert client.post(f"/api/projects/{pid}/repo/sync", json={}, headers=vh).status_code == 403
    assert client.post(
        f"/api/projects/{pid}/repo/push",
        json={"files": ["a.java"], "branch": "main", "commit_message": "x"},
        headers=vh,
    ).status_code == 403
    # 非成员与不存在 → 404(与可见项目区分开,不泄漏存在性)
    assert client.get(f"/api/projects/{pid}/repo/files", headers=oh).status_code == 404
    assert client.get("/api/projects/999999/repo/files", headers=vh).status_code == 404
    assert client.post("/api/projects/999999/repo/sync", json={}, headers=ah).status_code == 404


def test_repo_editor_can_sync(tmp_path, monkeypatch, client, db_session, make_user):
    """editor+ 可写外部系统:sync 真实拉取 bare 仓成功。"""
    import subprocess

    from app import git_service

    def _make_bare_origin(tmp_path):
        work = tmp_path / "origin_work"
        work.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=work, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=work, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=work, check=True)
        (work / "README.md").write_text("hi", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=work, check=True)
        subprocess.run(["git", "commit", "-qm", "i"], cwd=work, check=True)
        bare = tmp_path / "origin.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(work), str(bare)], check=True)
        return bare

    repos = tmp_path / "repos"
    repos.mkdir()
    monkeypatch.setattr(git_service.settings, "repos_dir", repos)
    bare = _make_bare_origin(tmp_path)
    ah = _admin_headers(client, db_session)
    pid = client.post(
        "/api/projects",
        json={"name": "editor 同步项目", "git_repo_url": f"file:///{bare.as_posix()}", "git_token": "tok"},
        headers=ah,
    ).json()["id"]
    # Task 3 写透落地:项目经 POST /api/projects 携 git 字段创建,api 仓行已由 create_project 产生;
    # 此处不再补种(重复种会撞 uq_autorepo_project_kind)
    eh = _auth(client, db_session, make_user, "jreditor", project_ids=[pid], role="editor")
    r = client.post(f"/api/projects/{pid}/repo/sync", json={}, headers=eh)
    assert r.status_code == 200
    assert r.json()["cloned"] is True or r.json()["updated"] is True
