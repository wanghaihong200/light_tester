"""Task 6:树路由(modules/cases/documents)项目级隔离测试。
_auth helper 从 tests/test_project_isolation.py(Task 5 修正版)复制为同型 helper。"""

CASE_PAYLOAD = {
    "title": "正确账号密码登录成功",
    "priority": "P0",
    "steps": [{"action": "输入账号", "expected": "显示掩码"}],
}


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


def _proj(client, ah, name):
    return client.post("/api/projects", json={"name": name}, headers=ah).json()["id"]


def _module(client, h, pid, name):
    return client.post(f"/api/projects/{pid}/modules", json={"name": name}, headers=h).json()


def _fp(client, h, module_id, name="功能点"):
    return client.post(f"/api/modules/{module_id}/feature-points", json={"name": name}, headers=h).json()


def _case(client, h, fp_id):
    return client.post(f"/api/feature-points/{fp_id}/cases", json=CASE_PAYLOAD, headers=h).json()


def test_modules_scoped(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    p1 = _proj(client, ah, "t1")
    p2 = _proj(client, ah, "t2")
    _module(client, ah, p1, "登录模块")
    uh = _auth(client, db_session, make_user, "treeuser", project_ids=[p2], role="editor")
    assert client.get(f"/api/projects/{p1}/tree", headers=uh).status_code == 404      # 不可见
    assert client.post(f"/api/projects/{p1}/modules", json={"name": "x"}, headers=uh).status_code == 404
    ok = client.post(f"/api/projects/{p2}/modules", json={"name": "我的模块"}, headers=uh)
    assert ok.status_code == 201                                                      # 自己的项目可写


def test_viewer_read_only_modules(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    p1 = _proj(client, ah, "ro")
    mod = _module(client, ah, p1, "只读模块")
    vh = _auth(client, db_session, make_user, "treeviewer", project_ids=[p1], role="viewer")
    assert client.get(f"/api/projects/{p1}/tree", headers=vh).status_code == 200      # 可读
    assert client.post(f"/api/projects/{p1}/modules", json={"name": "x"}, headers=vh).status_code == 403
    assert client.put(f"/api/modules/{mod['id']}", json={"name": "y"}, headers=vh).status_code == 403
    assert client.delete(f"/api/modules/{mod['id']}", headers=vh).status_code == 403


def test_module_object_endpoints_scoped(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    p1 = _proj(client, ah, "mo1")
    p2 = _proj(client, ah, "mo2")
    mod = _module(client, ah, p1, "target")
    eh = _auth(client, db_session, make_user, "modtor", project_ids=[p2], role="editor")
    assert client.put(f"/api/modules/{mod['id']}", json={"name": "hijack"}, headers=eh).status_code == 404
    assert client.delete(f"/api/modules/{mod['id']}", headers=eh).status_code == 404
    own = _module(client, eh, p2, "我的模块")
    r = client.put(f"/api/modules/{own['id']}", json={"name": "改名"}, headers=eh)
    assert r.status_code == 200 and r.json()["name"] == "改名"


def test_cases_scoped(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    p1 = _proj(client, ah, "c1")
    p2 = _proj(client, ah, "c2")
    mod = _module(client, ah, p1, "登录")
    fp = _fp(client, ah, mod["id"])
    case = _case(client, ah, fp["id"])
    oh = _auth(client, db_session, make_user, "caseoutsider", project_ids=[p2], role="editor")
    # 全部按对象回溯 project_id → 无关系即 404 不可见(非破坏性断言在前)
    assert client.get(f"/api/cases/{case['id']}", headers=oh).status_code == 404
    assert client.put(f"/api/cases/{case['id']}", json=CASE_PAYLOAD, headers=oh).status_code == 404
    assert client.patch(
        f"/api/cases/{case['id']}/execution", json={"executed_pass": True}, headers=oh
    ).status_code == 404
    assert client.post(f"/api/modules/{mod['id']}/feature-points", json={"name": "x"}, headers=oh).status_code == 404
    assert client.put(f"/api/feature-points/{fp['id']}", json={"name": "x"}, headers=oh).status_code == 404
    assert client.post(f"/api/feature-points/{fp['id']}/cases", json=CASE_PAYLOAD, headers=oh).status_code == 404
    # 破坏性断言收尾
    assert client.delete(f"/api/cases/{case['id']}", headers=oh).status_code == 404
    assert client.delete(f"/api/feature-points/{fp['id']}", headers=oh).status_code == 404
    # 自己的项目可写
    own_mod = _module(client, oh, p2, "我的模块")
    own_fp = _fp(client, oh, own_mod["id"], "我的功能点")
    assert own_fp["name"] == "我的功能点"
    assert client.post(f"/api/feature-points/{own_fp['id']}/cases", json=CASE_PAYLOAD, headers=oh).status_code == 201


def test_viewer_read_only_cases(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    p1 = _proj(client, ah, "cv")
    mod = _module(client, ah, p1, "登录")
    fp = _fp(client, ah, mod["id"])
    case = _case(client, ah, fp["id"])
    vh = _auth(client, db_session, make_user, "caseviewer", project_ids=[p1], role="viewer")
    assert client.get(f"/api/cases/{case['id']}", headers=vh).status_code == 200      # 可读
    assert client.put(f"/api/cases/{case['id']}", json=CASE_PAYLOAD, headers=vh).status_code == 403
    assert client.patch(
        f"/api/cases/{case['id']}/execution", json={"executed_pass": True}, headers=vh
    ).status_code == 403
    assert client.post(f"/api/modules/{mod['id']}/feature-points", json={"name": "x"}, headers=vh).status_code == 403
    assert client.delete(f"/api/cases/{case['id']}", headers=vh).status_code == 403


def test_documents_scoped(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    p1 = _proj(client, ah, "d1")
    p2 = _proj(client, ah, "d2")
    doc_id = client.post(
        f"/api/projects/{p1}/documents", files={"file": ("a.md", b"# hi", "text/markdown")}, headers=ah
    ).json()["id"]
    oh = _auth(client, db_session, make_user, "docoutsider", project_ids=[p2], role="editor")
    assert client.get(f"/api/projects/{p1}/documents", headers=oh).status_code == 404  # 不可见
    up = client.post(
        f"/api/projects/{p1}/documents", files={"file": ("b.md", b"# b", "text/markdown")}, headers=oh
    )
    assert up.status_code == 404
    assert client.get(f"/api/documents/{doc_id}/download", headers=oh).status_code == 404
    assert client.delete(f"/api/documents/{doc_id}", headers=oh).status_code == 404


def test_viewer_cannot_upload_document(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = _proj(client, ah, "d3")
    vh = _auth(client, db_session, make_user, "viewdoc", project_ids=[pid], role="viewer")
    r = client.post(
        f"/api/projects/{pid}/documents", files={"file": ("a.md", b"# hi", "text/markdown")}, headers=vh
    )
    assert r.status_code == 403                                                       # 角色不足
    assert client.get(f"/api/projects/{pid}/documents", headers=vh).status_code == 200  # 列表可读


def test_documents_roles_on_object_endpoints(client, db_session, make_user):
    ah = _admin_headers(client, db_session)
    pid = _proj(client, ah, "d4")
    doc_id = client.post(
        f"/api/projects/{pid}/documents", files={"file": ("a.md", b"# a", "text/markdown")}, headers=ah
    ).json()["id"]
    vh = _auth(client, db_session, make_user, "docviewer2", project_ids=[pid], role="viewer")
    assert client.get(f"/api/documents/{doc_id}/download", headers=vh).status_code == 403
    assert client.delete(f"/api/documents/{doc_id}", headers=vh).status_code == 403
    eh = _auth(client, db_session, make_user, "doceditor", project_ids=[pid], role="editor")
    up = client.post(
        f"/api/projects/{pid}/documents", files={"file": ("b.md", b"# b", "text/markdown")}, headers=eh
    )
    assert up.status_code == 201                                                      # editor 可上传
    dl = client.get(f"/api/documents/{up.json()['id']}/download", headers=eh)
    assert dl.status_code == 200 and "# b" in dl.text
    assert client.delete(f"/api/documents/{up.json()['id']}", headers=eh).status_code == 204
