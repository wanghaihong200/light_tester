"""计划 16 Task 10:触发编排 + preflight/触发/列表端点(file:// 仓 + FakeJenkins,绝不连真实例)。"""
import subprocess

import pytest

from app.models import (AutomationRepo, CiRun, ExecutionPlan, InterfaceCase,
                        JenkinsConnection, Project, ProjectMember)


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    u = make_user(db_session, name)
    for pid in project_ids:
        db_session.add(ProjectMember(project_id=pid, user_id=u.id, role=role))
    db_session.commit()
    r = client.post("/api/auth/login", json={"username": name, "password": "pw-" + name})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _seed_repo(tmp_path):
    """file:// 裸仓(master,含一个 RestAssured 测试类)→ 返回 origin 路径。"""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(origin)], check=True)
    src = tmp_path / "seed"
    src.mkdir()
    (src / "pom.xml").write_text("<project/>", encoding="utf-8")
    tj = src / "src/test/java/com/x"
    tj.mkdir(parents=True)
    (tj / "AuthApiTest.java").write_text(
        'package com.x;\nimport org.testng.annotations.Test;\n'
        'public class AuthApiTest {\n    @Test\n    public void loginOk() { }\n}\n',
        encoding="utf-8")
    for args in (["init", "-q", "-b", "master"], ["add", "."]):
        subprocess.run(["git", "-C", str(src), *args], check=True)
    subprocess.run(["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True)
    subprocess.run(["git", "-C", str(src), "push", "-q", str(origin), "master"], check=True)
    return origin


@pytest.fixture()
def env(tmp_path, monkeypatch, db_session, fake_jenkins, monkeypatched_client):
    """项目 + api 仓 + JenkinsConnection + 注册表(active: loginOk)+ 接口计划。"""
    from app.config import settings

    monkeypatch.setattr(settings, "repos_dir", tmp_path / "repos")
    origin = _seed_repo(tmp_path)
    proj = Project(name="runs")
    db_session.add(proj)
    db_session.commit()
    db_session.add(AutomationRepo(project_id=proj.id, kind="api", repo_url=origin.as_uri()))
    db_session.add(JenkinsConnection(id=1, base_url="http://jk", api_user="a", api_token="t"))
    db_session.add(InterfaceCase(project_id=proj.id, branch="master",
                                 class_name="com.x.AuthApiTest", method="loginOk",
                                 status="active"))
    plan = ExecutionPlan(project_id=proj.id, name="接口回归", kind="api", branch="master",
                         selection=[{"ref": "com.x.AuthApiTest#loginOk",
                                     "class_name": "com.x.AuthApiTest", "method": "loginOk"}])
    db_session.add(plan)
    db_session.commit()
    return {"project_id": proj.id, "plan_id": plan.id, "origin": origin}


def test_preflight_reports_freshness_and_material(client, db_session, make_user, env):
    pid, plan_id = env["project_id"], env["plan_id"]
    h = _auth(client, db_session, make_user, "runner1", project_ids=[pid])
    r = client.post(f"/api/projects/{pid}/ci-runs/preflight",
                    json={"plan_ids": [plan_id]}, headers=h)
    assert r.status_code == 200
    item = r.json()[0]
    assert item["plan_id"] == plan_id and item["valid"] == 1 and item["missing"] == 0
    assert item["freshness"]["stale"] is False and item["error"] is None


def test_trigger_creates_queued_run_with_params(client, db_session, make_user, env, fake_jenkins):
    pid, plan_id = env["project_id"], env["plan_id"]
    h = _auth(client, db_session, make_user, "runner2", project_ids=[pid])
    r = client.post(f"/api/projects/{pid}/ci-runs",
                    json={"plan_ids": [plan_id], "confirm_stale": False}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["failures"] == []
    run = body["runs"][0]
    assert run["status"] == "queued" and run["build_number"] == 1
    assert all(s.get("skipped") is not True for s in run["selection"])
    # 触发参数:仓地址、分支、类型、选择串
    sent = fake_jenkins.params_log[0]
    assert sent["BRANCH"] == "master" and sent["KIND"] == "api"
    assert sent["SELECTION"] == "com.x.AuthApiTest#loginOk"
    assert sent["REPO_URL"] == env["origin"].as_uri()


def test_trigger_stale_409_then_confirm(client, db_session, make_user, env, tmp_path):
    from app import git_service

    pid, plan_id = env["project_id"], env["plan_id"]
    h = _auth(client, db_session, make_user, "runner3", project_ids=[pid])
    # 制造未推送产物:先 sync 到位,再丢一个 untracked 文件
    repo = db_session.query(AutomationRepo).filter_by(project_id=pid, kind="api").one()
    git_service.sync_repo(repo, "master")
    (git_service.working_copy_path(repo) / "test_new_thing.py").write_text("x", encoding="utf-8")
    r = client.post(f"/api/projects/{pid}/ci-runs",
                    json={"plan_ids": [plan_id], "confirm_stale": False}, headers=h)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["freshness"]["stale"] is True and detail["freshness"]["dirty_files"] >= 1
    r2 = client.post(f"/api/projects/{pid}/ci-runs",
                     json={"plan_ids": [plan_id], "confirm_stale": True}, headers=h)
    assert r2.status_code == 200
    run = r2.json()["runs"][0]
    assert run["freshness"]["stale"] is True  # 快照留痕


def test_trigger_all_material_missing_400(client, db_session, make_user, env):
    from app.models import InterfaceCase as IC

    pid, plan_id = env["project_id"], env["plan_id"]
    db_session.query(IC).filter_by(project_id=pid).update({"status": "stale"})
    db_session.commit()
    h = _auth(client, db_session, make_user, "runner4", project_ids=[pid])
    r = client.post(f"/api/projects/{pid}/ci-runs",
                    json={"plan_ids": [plan_id], "confirm_stale": True}, headers=h)
    assert r.status_code == 200  # 批量端点不抛
    assert r.json()["runs"] == [] and "物料" in r.json()["failures"][0]["error"]


def test_list_and_get_runs(client, db_session, make_user, env, fake_jenkins):
    pid, plan_id = env["project_id"], env["plan_id"]
    h = _auth(client, db_session, make_user, "runner5", project_ids=[pid], role="viewer")
    he = _auth(client, db_session, make_user, "runner5e", project_ids=[pid])
    client.post(f"/api/projects/{pid}/ci-runs",
                json={"plan_ids": [plan_id], "confirm_stale": True}, headers=he)
    lst = client.get(f"/api/projects/{pid}/ci-runs", headers=h)
    assert lst.status_code == 200 and len(lst.json()) == 1
    rid = lst.json()[0]["id"]
    assert client.get(f"/api/ci-runs/{rid}", headers=h).json()["plan_name"] == "接口回归"
    # 非成员不可见
    ho = _auth(client, db_session, make_user, "runner5o")
    assert client.get(f"/api/ci-runs/{rid}", headers=ho).status_code == 404


def test_preflight_branch_missing_reports_error(client, db_session, make_user, env):
    from sqlalchemy import update as sa_update

    pid, plan_id = env["project_id"], env["plan_id"]
    db_session.execute(sa_update(ExecutionPlan).where(ExecutionPlan.id == plan_id)
                       .values(branch="no-such-branch"))
    db_session.commit()
    h = _auth(client, db_session, make_user, "runner6", project_ids=[pid])
    r = client.post(f"/api/projects/{pid}/ci-runs/preflight",
                    json={"plan_ids": [plan_id]}, headers=h)
    item = r.json()[0]
    assert item["error"] and "分支" in item["error"]
