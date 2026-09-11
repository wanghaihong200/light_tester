"""规则组 API:CRUD/组内嵌规则/两级 reorder/权限(计划 15 T6)。

对 brief 样例的仓内现状对齐(非行为偏离):
- 登录响应字段是 token 不是 access_token(同 tests/test_mock_instances_api.py 已对齐过的笔误);
- mock_instances/mocks 相关表已在 conftest._TABLES,无需本文件再加 TRUNCATE 清理。
"""
from app.models import MockInstance, Project


def _login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "pw-" + username})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _project_inst(db, name, port, owner=None):
    p = Project(name=name)
    db.add(p)
    db.commit()
    if owner is not None:
        from app.models import ProjectMember
        db.add(ProjectMember(project_id=p.id, user_id=owner.id, role="owner"))
        db.commit()
    inst = MockInstance(project_id=p.id, name="s", port=port, token="t" * 32)
    db.add(inst)
    db.commit()
    return inst


def _mk_group(client, h, iid, method="GET", path="/a", **kw):
    r = client.post(f"/api/mock-instances/{iid}/rule-groups",
                    json={"method": method, "path_template": path, **kw}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def _mk_rule(client, h, iid, gid, **kw):
    r = client.post(f"/api/mock-instances/{iid}/rules",
                    json={"group_id": gid, "conditions": [], "response_status": 200, **kw},
                    headers=h)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_group_and_duplicate_route_400(client, db_session, make_user):
    admin = make_user(db_session, "adm30", is_admin=True)
    inst = _project_inst(db_session, "p-group-1", 19061)
    h = _login(client, admin.username)

    r = client.post(f"/api/mock-instances/{inst.id}/rule-groups",
                    json={"method": "get", "path_template": "/a/{id}", "description": "d"},
                    headers=h)
    assert r.status_code == 201
    assert r.json()["method"] == "GET"                      # 入参小写归一为大写
    assert r.json()["path_template"] == "/a/{id}"
    assert r.json()["rules"] == []
    assert r.json()["enabled"] is True
    assert r.json()["sort_order"] == 1

    dup = client.post(f"/api/mock-instances/{inst.id}/rule-groups",
                      json={"method": "GET", "path_template": "/a/{id}"}, headers=h)
    assert dup.status_code == 400                            # 同实例重路(未删组)

    bad = client.post(f"/api/mock-instances/{inst.id}/rule-groups",
                      json={"method": "PURGE", "path_template": "/x"}, headers=h)
    assert bad.status_code == 400
    bad2 = client.post(f"/api/mock-instances/{inst.id}/rule-groups",
                       json={"method": "GET", "path_template": "no-slash"}, headers=h)
    assert bad2.status_code == 400


def test_create_rule_requires_group_of_instance(client, db_session, make_user):
    """组下建规则:组不存在/软删 → 404;组属其它实例 → 400。"""
    admin = make_user(db_session, "adm31", is_admin=True)
    inst = _project_inst(db_session, "p-group-2", 19062)
    other = _project_inst(db_session, "p-group-2b", 19063)
    h = _login(client, admin.username)
    og = _mk_group(client, h, other.id, method="POST", path="/o")

    missing = client.post(f"/api/mock-instances/{inst.id}/rules",
                          json={"group_id": 99999, "conditions": []}, headers=h)
    assert missing.status_code == 404
    cross = client.post(f"/api/mock-instances/{inst.id}/rules",
                        json={"group_id": og["id"], "conditions": []}, headers=h)
    assert cross.status_code == 400

    g = _mk_group(client, h, inst.id)
    ok = client.post(f"/api/mock-instances/{inst.id}/rules",
                     json={"group_id": g["id"], "conditions": [], "response_status": 200},
                     headers=h)
    assert ok.status_code == 201
    assert ok.json()["group_id"] == g["id"]


def test_nested_rules_ordered(client, db_session, make_user):
    """列表端点内嵌组内规则且按组内序;组间 reorder 后嵌套顺序跟随。"""
    admin = make_user(db_session, "adm32", is_admin=True)
    inst = _project_inst(db_session, "p-group-3", 19064)
    h = _login(client, admin.username)
    gid = _mk_group(client, h, inst.id)["id"]
    r1 = _mk_rule(client, h, inst.id, gid)
    r2 = _mk_rule(client, h, inst.id, gid, response_status=404)
    api = client
    api.put(f"/api/mock-rule-groups/{gid}/rules/reorder",
            json={"rule_ids": [r2["id"], r1["id"]]}, headers=h)
    groups = api.get(f"/api/mock-instances/{inst.id}/rule-groups", headers=h).json()
    assert [r["id"] for r in groups[0]["rules"]] == [r2["id"], r1["id"]]


def test_update_group_rename_unique_check(client, db_session, make_user):
    admin = make_user(db_session, "adm33", is_admin=True)
    inst = _project_inst(db_session, "p-group-4", 19065)
    h = _login(client, admin.username)
    a = _mk_group(client, h, inst.id, method="GET", path="/a")
    b = _mk_group(client, h, inst.id, method="POST", path="/b")

    conflict = client.put(f"/api/mock-rule-groups/{b['id']}",
                          json={"method": "GET", "path_template": "/a"}, headers=h)
    assert conflict.status_code == 400                       # 改名撞已有组

    bad = client.put(f"/api/mock-rule-groups/{b['id']}",
                     json={"path_template": "no-slash"}, headers=h)
    assert bad.status_code == 400

    ok = client.put(f"/api/mock-rule-groups/{b['id']}",
                    json={"path_template": "/c"}, headers=h)
    assert ok.status_code == 200
    assert ok.json()["method"] == "POST" and ok.json()["path_template"] == "/c"
    self_ok = client.put(f"/api/mock-rule-groups/{b['id']}",
                         json={"method": "post", "path_template": "/c"}, headers=h)
    assert self_ok.status_code == 200                        # 自己撞自己(exclude)放行
    assert self_ok.json()["method"] == "POST"


def test_update_group_enabled_and_description_patch(client, db_session, make_user):
    admin = make_user(db_session, "adm34", is_admin=True)
    inst = _project_inst(db_session, "p-group-5", 19066)
    h = _login(client, admin.username)
    g = _mk_group(client, h, inst.id, description="d1")

    off = client.put(f"/api/mock-rule-groups/{g['id']}", json={"enabled": False}, headers=h)
    assert off.status_code == 200 and off.json()["enabled"] is False
    cleared = client.put(f"/api/mock-rule-groups/{g['id']}",
                         json={"description": None}, headers=h)
    assert cleared.status_code == 200 and cleared.json()["description"] is None
    assert cleared.json()["enabled"] is False                # 未提及字段不被重置


def test_delete_group_soft_deletes_rules(client, db_session, make_user):
    """显式删组=组连同组内规则一并软删(空组保留原则只约束"逐条删规则")。"""
    admin = make_user(db_session, "adm35", is_admin=True)
    inst = _project_inst(db_session, "p-group-6", 19067)
    h = _login(client, admin.username)
    gid = _mk_group(client, h, inst.id)["id"]
    for _ in range(2):
        _mk_rule(client, h, inst.id, gid)
    assert client.delete(f"/api/mock-rule-groups/{gid}", headers=h).status_code == 204
    assert client.delete(f"/api/mock-rule-groups/{gid}", headers=h).status_code == 404  # 已删再删 404
    assert client.get(f"/api/mock-instances/{inst.id}/rule-groups", headers=h).json() == []
    assert client.get(f"/api/mock-instances/{inst.id}/rules", headers=h).json() == []


def test_group_reorder_full_set_validation(client, db_session, make_user):
    """组 reorder=实例下全量新序:缺/多(跨实例)/重复 → 400;成功后组序持久。"""
    admin = make_user(db_session, "adm36", is_admin=True)
    inst = _project_inst(db_session, "p-group-7", 19068)
    other = _project_inst(db_session, "p-group-7b", 19069)
    h = _login(client, admin.username)
    g1 = _mk_group(client, h, inst.id, method="GET", path="/1")["id"]
    g2 = _mk_group(client, h, inst.id, method="GET", path="/2")["id"]
    g3 = _mk_group(client, h, inst.id, method="GET", path="/3")["id"]
    og = _mk_group(client, h, other.id, method="GET", path="/o")["id"]

    url = f"/api/mock-instances/{inst.id}/rule-groups/reorder"
    assert client.put(url, json={"group_ids": [g1, g2]}, headers=h).status_code == 400      # 缺
    assert client.put(url, json={"group_ids": [g1, g2, g3, og]}, headers=h).status_code == 400  # 多(跨实例)
    assert client.put(url, json={"group_ids": [g1, g1, g3]}, headers=h).status_code == 400  # 重复
    ok = client.put(url, json={"group_ids": [g3, g1, g2]}, headers=h)
    assert ok.status_code == 200
    assert [g["id"] for g in ok.json()] == [g3, g1, g2]
    listed = client.get(f"/api/mock-instances/{inst.id}/rule-groups", headers=h).json()
    assert [g["id"] for g in listed] == [g3, g1, g2]


def test_group_rules_reorder_full_set_validation(client, db_session, make_user):
    admin = make_user(db_session, "adm37", is_admin=True)
    inst = _project_inst(db_session, "p-group-8", 19070)
    h = _login(client, admin.username)
    gid = _mk_group(client, h, inst.id, method="GET", path="/a")["id"]
    gid2 = _mk_group(client, h, inst.id, method="GET", path="/b")["id"]
    r1 = _mk_rule(client, h, inst.id, gid)["id"]
    r2 = _mk_rule(client, h, inst.id, gid)["id"]
    r3 = _mk_rule(client, h, inst.id, gid)["id"]
    outside = _mk_rule(client, h, inst.id, gid2)["id"]

    url = f"/api/mock-rule-groups/{gid}/rules/reorder"
    assert client.put(url, json={"rule_ids": [r1, r2]}, headers=h).status_code == 400       # 缺
    assert client.put(url, json={"rule_ids": [r1, r2, r3, outside]}, headers=h).status_code == 400  # 他组规则
    assert client.put(url, json={"rule_ids": [r1, r1, r3]}, headers=h).status_code == 400   # 重复
    ok = client.put(url, json={"rule_ids": [r3, r2, r1]}, headers=h)
    assert ok.status_code == 200
    assert [r["id"] for r in ok.json()] == [r3, r2, r1]
    listed = client.get(f"/api/mock-instances/{inst.id}/rules", headers=h).json()
    assert [r["id"] for r in listed if r["group_id"] == gid] == [r3, r2, r1]


def test_group_permission_matrix(client, db_session, make_user):
    """viewer 读 200/写 403;非成员一律 404 不泄漏存在性。"""
    admin = make_user(db_session, "adm38", is_admin=True)
    viewer = make_user(db_session, "vw38")
    outsider = make_user(db_session, "out38")
    inst = _project_inst(db_session, "p-group-9", 19071)
    from app.models import ProjectMember
    db_session.add(ProjectMember(project_id=inst.project_id, user_id=viewer.id, role="viewer"))
    db_session.commit()
    ah, vh, oh = (_login(client, u.username) for u in (admin, viewer, outsider))
    gid = _mk_group(client, ah, inst.id)["id"]

    assert client.get(f"/api/mock-instances/{inst.id}/rule-groups", headers=vh).status_code == 200
    assert client.post(f"/api/mock-instances/{inst.id}/rule-groups",
                       json={"method": "GET", "path_template": "/v"}, headers=vh).status_code == 403
    assert client.put(f"/api/mock-rule-groups/{gid}",
                      json={"enabled": False}, headers=vh).status_code == 403
    assert client.put(f"/api/mock-instances/{inst.id}/rule-groups/reorder",
                      json={"group_ids": [gid]}, headers=vh).status_code == 403
    assert client.delete(f"/api/mock-rule-groups/{gid}", headers=vh).status_code == 403

    assert client.get(f"/api/mock-instances/{inst.id}/rule-groups", headers=oh).status_code == 404
    assert client.post(f"/api/mock-instances/{inst.id}/rule-groups",
                       json={"method": "GET", "path_template": "/x"}, headers=oh).status_code == 404
    assert client.put(f"/api/mock-rule-groups/{gid}",
                      json={"enabled": False}, headers=oh).status_code == 404
    assert client.delete(f"/api/mock-rule-groups/{gid}", headers=oh).status_code == 404
