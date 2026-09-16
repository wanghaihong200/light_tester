"""计划 16 Task 7:注册表增量合并 + 扫描/列表端点。"""
import subprocess

import pytest

from app.cicd import registry
from app.models import AutomationRepo, InterfaceCase, Project


def test_sync_registry_merge(db_session):
    db_session.add(Project(id=1, name="p"))  # MySQL FK:interface_cases.project_id 需真实项目行
    db_session.commit()
    db_session.add_all([
        InterfaceCase(project_id=1, branch="master", class_name="com.x.A", method="keep",
                      status="active"),
        InterfaceCase(project_id=1, branch="master", class_name="com.x.A", method="gone",
                      status="active"),
        InterfaceCase(project_id=1, branch="dev", class_name="com.x.A", method="other",
                      status="active"),
    ])
    db_session.commit()
    stat = registry.sync_registry(db_session, 1, "master",
                                  scanned=[{"class_name": "com.x.A", "method": "keep",
                                            "file_path": "src/test/java/com/x/A.java",
                                            "framework": "testng"},
                                           {"class_name": "com.x.A", "method": "new1",
                                            "file_path": "src/test/java/com/x/A.java",
                                            "framework": "testng"}],
                                  commit="abc1234")
    assert (stat["added"], stat["stale"]) == (1, 1)
    rows = db_session.query(InterfaceCase).filter_by(project_id=1, branch="master").all()
    by = {(r.class_name, r.method): r.status for r in rows}
    assert by == {("com.x.A", "keep"): "active", ("com.x.A", "gone"): "stale",
                  ("com.x.A", "new1"): "active"}
    # dev 分支不受 master 扫描影响
    assert db_session.query(InterfaceCase).filter_by(branch="dev").count() == 1


def test_reactivate_after_rescan(db_session):
    db_session.add(Project(id=1, name="p"))  # MySQL FK:interface_cases.project_id 需真实项目行
    db_session.commit()
    db_session.add(InterfaceCase(project_id=1, branch="master", class_name="com.x.A",
                                 method="m1", status="stale"))
    db_session.commit()
    registry.sync_registry(db_session, 1, "master",
                           scanned=[{"class_name": "com.x.A", "method": "m1",
                                     "file_path": "p.java", "framework": "junit5"}],
                           commit="def")
    row = db_session.query(InterfaceCase).filter_by(project_id=1, branch="master").one()
    assert row.status == "active" and row.framework == "junit5"


@pytest.fixture()
def api_repo(tmp_path, monkeypatch, db_session):
    """建 file:// 裸仓(含一个 TestNG 测试类)+ AutomationRepo 行;repos_dir 指向 tmp。"""
    from app.config import settings

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
    subprocess.run(["git", "-C", str(src), "init", "-q", "-b", "master"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "."], check=True)
    subprocess.run(["git", "-C", str(src), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "init"], check=True)
    subprocess.run(["git", "-C", str(src), "push", "-q", str(origin), "master"], check=True)

    monkeypatch.setattr(settings, "repos_dir", tmp_path / "repos")
    proj = Project(name="rp")
    db_session.add(proj)
    db_session.commit()
    # automation_repos 不在 conftest._TABLES 清理列,跨用例残留行会撞 (project_id, kind) 唯一键
    db_session.query(AutomationRepo).delete()
    db_session.commit()
    repo = AutomationRepo(project_id=proj.id, kind="api", repo_url=origin.as_uri())
    db_session.add(repo)
    db_session.commit()
    return {"project_id": proj.id, "repo_id": repo.id}


def _auth(client, db_session, make_user, name, *, project_ids=(), role="editor"):
    from app.models import ProjectMember

    u = make_user(db_session, name)
    for pid in project_ids:
        db_session.add(ProjectMember(project_id=pid, user_id=u.id, role=role))
    db_session.commit()
    r = client.post("/api/auth/login", json={"username": name, "password": "pw-" + name})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_scan_and_list_endpoints(client, db_session, make_user, api_repo):
    pid = api_repo["project_id"]
    h = _auth(client, db_session, make_user, "scanner", project_ids=[pid])
    r = client.post(f"/api/projects/{pid}/interface-cases/scan",
                    json={"branch": "master"}, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["added"] == 1 and body["active"] == 1 and body["stale"] == 0
    r2 = client.get(f"/api/projects/{pid}/interface-cases?branch=master", headers=h)
    rows = r2.json()
    assert [(x["class_name"], x["method"], x["status"]) for x in rows] == \
        [("com.x.AuthApiTest", "loginOk", "active")]


def test_scan_requires_editor(client, db_session, make_user, api_repo):
    pid = api_repo["project_id"]
    h = _auth(client, db_session, make_user, "viewer1", project_ids=[pid], role="viewer")
    r = client.post(f"/api/projects/{pid}/interface-cases/scan",
                    json={"branch": "master"}, headers=h)
    assert r.status_code == 403
