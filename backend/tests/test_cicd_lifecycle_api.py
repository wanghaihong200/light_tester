"""计划 16 Task 12:SSE 终态快照 / 停止 / 重跑。"""
import pytest

from app.models import (AutomationRepo, CiRun, ExecutionPlan, InterfaceCase,
                        JenkinsConnection, Project, ProjectMember)


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    u = make_user(db_session, name)
    for pid in project_ids:
        db_session.add(ProjectMember(project_id=pid, user_id=u.id, role=role))
    db_session.commit()
    r = client.post("/api/auth/login", json={"username": name, "password": "pw-" + name})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _mk_run(db_session, project_id=1, status="success", plan_id=None) -> CiRun:
    if plan_id is None:
        # ci_runs 对 execution_plans 有真实 FK(测试库强制):先落父行并提交,再插 run
        plan = ExecutionPlan(project_id=project_id, name="p", kind="api",
                             branch="master", selection=[])
        db_session.add(plan)
        db_session.commit()
        plan_id = plan.id
    run = CiRun(project_id=project_id, plan_id=plan_id, plan_name="p", kind="api",
                branch="master", selection=[], status=status, jenkins_job="j1",
                build_number=1, total=1, passed=1, results=[])
    db_session.add(run)
    db_session.commit()
    return run


@pytest.fixture()
def env16(tmp_path, monkeypatch, db_session):
    """项目+api 仓+连接+计划(带 active 选择项)+一条成功历史记录;种子仓复用 Task 10 的 _seed_repo。"""
    from app.config import settings
    from tests.test_cicd_runs_api import _seed_repo

    monkeypatch.setattr(settings, "repos_dir", tmp_path / "repos")
    origin = _seed_repo(tmp_path)
    proj = Project(name="rr")
    db_session.add(proj)
    db_session.commit()
    db_session.add(AutomationRepo(project_id=proj.id, kind="api", repo_url=origin.as_uri()))
    db_session.add(JenkinsConnection(id=1, base_url="http://jk", api_user="a", api_token="t"))
    db_session.add(InterfaceCase(project_id=proj.id, branch="master",
                                 class_name="com.x.AuthApiTest", method="loginOk",
                                 status="active"))
    plan = ExecutionPlan(project_id=proj.id, name="rr计划", kind="api", branch="master",
                         selection=[{"ref": "com.x.AuthApiTest#loginOk",
                                     "class_name": "com.x.AuthApiTest", "method": "loginOk"}])
    db_session.add(plan)
    db_session.commit()
    run = _mk_run(db_session, project_id=proj.id, plan_id=plan.id, status="success")
    return {"project_id": proj.id, "plan_id": plan.id, "run": run}


def test_sse_terminal_snapshot(client, db_session, make_user):
    """终态 SSE 只发 status+snapshot;console 全量改由 REST /console 端点提供,
    SSE 不再回放日志(根治尾部重复与不完整两类问题,2026-09-17 详情页改版)。"""
    proj = Project(name="sse")
    db_session.add(proj)
    db_session.commit()
    run = _mk_run(db_session, project_id=proj.id)
    h = _auth(client, db_session, make_user, "ssev", project_ids=[proj.id], role="viewer")
    token = h["Authorization"].split(" ")[1]
    with client.stream("GET", f"/api/ci-runs/{run.id}/events?token={token}") as r:
        assert r.status_code == 200
        body = b"".join(r.iter_bytes()).decode()
    assert '"type": "status"' in body or '"type":"status"' in body
    assert '"type": "snapshot"' in body or '"type":"snapshot"' in body
    assert '"type": "log"' not in body  # 日志归 REST,直播帧只在活跃期出现


def test_console_endpoint_full_log(client, db_session, make_user, monkeypatch):
    """全量日志端点:终态 run 详情页经 REST 拉完整 console.log(不再受 8KB 尾部限制)。"""
    from app.config import settings

    proj = Project(name="clog")
    db_session.add(proj)
    db_session.commit()
    run = _mk_run(db_session, project_id=proj.id, status="success")
    d = settings.ci_data_dir / "runs" / str(run.id)
    d.mkdir(parents=True, exist_ok=True)
    content = "Started by user hi\n" + ("[Pipeline] line\n" * 2000) + "Finished: SUCCESS\n"
    (d / "console.log").write_text(content, encoding="utf-8")
    h = _auth(client, db_session, make_user, "clogv", project_ids=[proj.id], role="viewer")
    r = client.get(f"/api/ci-runs/{run.id}/console", headers=h)
    assert r.status_code == 200
    assert r.text == content  # 全量,无截断
    assert "text/plain" in r.headers["content-type"]


def test_console_endpoint_missing_file_returns_empty(client, db_session, make_user):
    proj = Project(name="clog2")
    db_session.add(proj)
    db_session.commit()
    run = _mk_run(db_session, project_id=proj.id, status="queued")  # 尚无日志文件
    h = _auth(client, db_session, make_user, "clog2v", project_ids=[proj.id], role="viewer")
    r = client.get(f"/api/ci-runs/{run.id}/console", headers=h)
    assert r.status_code == 200
    assert r.text == ""


def test_stop_running_run(client, db_session, make_user, fake_jenkins, monkeypatched_client):
    proj = Project(name="stop")
    db_session.add(proj)
    db_session.commit()
    db_session.add(JenkinsConnection(id=1, base_url="http://jk", api_user="a", api_token="t"))
    db_session.commit()
    fake_jenkins.jobs.add("j1")
    n = fake_jenkins.trigger("j1")
    run = _mk_run(db_session, project_id=proj.id, status="running")
    run.build_number = n
    db_session.commit()
    h = _auth(client, db_session, make_user, "stopper", project_ids=[proj.id])
    r = client.post(f"/api/ci-runs/{run.id}/stop", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "aborted"
    assert fake_jenkins.stopped == [("j1", n)]


def test_stop_finished_run_400(client, db_session, make_user):
    proj = Project(name="stop2")
    db_session.add(proj)
    db_session.commit()
    run = _mk_run(db_session, project_id=proj.id, status="success")
    h = _auth(client, db_session, make_user, "stopper2", project_ids=[proj.id])
    assert client.post(f"/api/ci-runs/{run.id}/stop", headers=h).status_code == 400


def test_rerun_creates_new_run(client, db_session, make_user, env16, fake_jenkins,
                              monkeypatched_client):
    pid, plan_id, old = env16["project_id"], env16["plan_id"], env16["run"]
    h = _auth(client, db_session, make_user, "rrun", project_ids=[pid])
    r = client.post(f"/api/ci-runs/{old.id}/rerun", headers=h)
    assert r.status_code == 201
    assert r.json()["id"] != old.id and r.json()["plan_id"] == plan_id


def test_rerun_plan_deleted_400(client, db_session, make_user):
    proj = Project(name="rr2")
    db_session.add(proj)
    db_session.commit()
    plan = ExecutionPlan(project_id=proj.id, name="x", kind="api", branch="master", selection=[])
    db_session.add(plan)
    db_session.commit()
    run = _mk_run(db_session, project_id=proj.id, plan_id=plan.id)
    h = _auth(client, db_session, make_user, "rr2u", project_ids=[proj.id])
    client.delete(f"/api/ci-plans/{plan.id}", headers=h)
    assert client.post(f"/api/ci-runs/{run.id}/rerun", headers=h).status_code == 400
