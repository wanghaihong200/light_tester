"""规则/命中 API:CRUD/挂组校验/组内 reorder/hits 过滤与清空/权限(计划 13 T7,计划 15 T6 改两级)。

对 brief 样例的仓内现状对齐(非行为偏离):
- 登录响应字段是 token 不是 access_token(同 tests/test_mock_instances_api.py 已对齐过的笔误);
- mock_instances/mocks 相关表已在 conftest._TABLES,无需本文件再加 TRUNCATE 清理。
"""
from app.models import MockHit, MockInstance, MockRule, MockRuleGroup, Project


def _login(client, username):
    r = client.post("/api/auth/login", json={"username": username, "password": "pw-" + username})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _project_inst(db, name, port):
    p = Project(name=name)
    db.add(p)
    db.commit()
    inst = MockInstance(project_id=p.id, name="s", port=port, token="t" * 32)
    db.add(inst)
    db.commit()
    return inst


def _group(db, inst, method="GET", path="/g"):
    g = MockRuleGroup(instance_id=inst.id, method=method, path_template=path)
    db.add(g)
    db.commit()
    return g


def test_rule_crud_and_group_validation(client, db_session, make_user):
    admin = make_user(db_session, "adm7", is_admin=True)
    p = Project(name="p-rule-1")
    db_session.add(p)
    db_session.commit()
    inst = MockInstance(project_id=p.id, name="s", port=19051, token="t" * 32)
    db_session.add(inst)
    db_session.commit()
    group = _group(db_session, inst, method="GET", path="/users/{id}")
    h = _login(client, "adm7")

    r = client.post(f"/api/mock-instances/{inst.id}/rules",
                    json={"group_id": group.id,
                          "conditions": [{"scope": "query", "key": "v", "match": "eq", "value": "2"}],
                          "response_status": 200, "response_body": "ok"}, headers=h)
    assert r.status_code == 201
    assert r.json()["group_id"] == group.id
    rid = r.json()["id"]

    missing = client.post(f"/api/mock-instances/{inst.id}/rules",
                          json={"group_id": 99999, "conditions": []}, headers=h)
    assert missing.status_code == 404                # 组不存在

    inst2 = MockInstance(project_id=p.id, name="s2", port=19055, token="t" * 32)
    db_session.add(inst2)
    db_session.commit()
    other_group = _group(db_session, inst2, method="GET", path="/other")
    cross = client.post(f"/api/mock-instances/{inst.id}/rules",
                        json={"group_id": other_group.id, "conditions": []}, headers=h)
    assert cross.status_code == 400                  # 组属其它实例

    up = client.put(f"/api/mock-rules/{rid}", json={"response_status": 201}, headers=h)
    assert up.status_code == 200 and up.json()["response_status"] == 201
    assert client.delete(f"/api/mock-rules/{rid}", headers=h).status_code == 204
    got = client.get(f"/api/mock-instances/{inst.id}/rules", headers=h)
    assert all(rule["id"] != rid for rule in got.json())


def test_partial_patch_enabled_keeps_enable_template(client, db_session, make_user):
    """回归:MockRulePatch 漏覆写 enable_template 时,仅发 {"enabled"} 的部分 PATCH
    会把模板开关静默重置为 False(规则列表启停开关的典型载荷)。"""
    admin = make_user(db_session, "adm10", is_admin=True)
    inst = _project_inst(db_session, "p-rule-4", 19054)
    group = _group(db_session, inst, path="/t")
    h = _login(client, "adm10")
    r = client.post(f"/api/mock-instances/{inst.id}/rules",
                    json={"group_id": group.id, "enable_template": True}, headers=h)
    assert r.status_code == 201 and r.json()["enable_template"] is True
    rid = r.json()["id"]

    off = client.put(f"/api/mock-rules/{rid}", json={"enabled": False}, headers=h)
    assert off.status_code == 200
    assert off.json()["enabled"] is False
    assert off.json()["enable_template"] is True    # 仅改 enabled 不得重置模板开关
    on = client.put(f"/api/mock-rules/{rid}", json={"enabled": True}, headers=h)
    assert on.status_code == 200
    assert on.json()["enabled"] is True
    assert on.json()["enable_template"] is True


def test_rule_reorder_within_group(client, db_session, make_user):
    admin = make_user(db_session, "adm8", is_admin=True)
    inst = _project_inst(db_session, "p-rule-2", 19052)
    group = _group(db_session, inst)
    ids = []
    for i in range(3):
        rule = MockRule(instance_id=inst.id, group_id=group.id, sort_order=i)
        db_session.add(rule)
        db_session.commit()
        ids.append(rule.id)
    h = _login(client, "adm8")
    r = client.put(f"/api/mock-rule-groups/{group.id}/rules/reorder",
                   json={"rule_ids": [ids[2], ids[0], ids[1]]}, headers=h)
    assert r.status_code == 200
    ordered = client.get(f"/api/mock-instances/{inst.id}/rules", headers=h).json()
    assert [x["id"] for x in ordered] == [ids[2], ids[0], ids[1]]
    partial = client.put(f"/api/mock-rule-groups/{group.id}/rules/reorder",
                         json={"rule_ids": [ids[0]]}, headers=h)
    assert partial.status_code == 400


def test_hits_list_filter_detail_clear(client, db_session, make_user):
    admin = make_user(db_session, "adm9", is_admin=True)
    viewer = make_user(db_session, "vw9")
    from app.models import ProjectMember
    p = Project(name="p-rule-3")
    db_session.add(p)
    db_session.commit()
    inst = MockInstance(project_id=p.id, name="s", port=19053, token="t" * 32)
    db_session.add(inst)
    db_session.commit()
    group = _group(db_session, inst)
    rule = MockRule(instance_id=inst.id, group_id=group.id)
    db_session.add(rule)
    db_session.commit()
    for matched, status in [(True, 200), (False, 404), (False, 404)]:
        db_session.add(MockHit(instance_id=inst.id, rule_id=rule.id if matched else None,
                               method="GET", path="/x", request_headers={"a": "b"},
                               request_body="raw", matched=matched, response_status=status))
    db_session.commit()
    ah, vh = _login(client, "adm9"), _login(client, "vw9")
    db_session.add(ProjectMember(project_id=p.id, user_id=viewer.id, role="viewer"))
    db_session.commit()

    assert len(client.get(f"/api/mock-instances/{inst.id}/hits", headers=vh).json()) == 3  # viewer 可读
    misses = client.get(f"/api/mock-instances/{inst.id}/hits?filter=unmatched", headers=ah).json()
    assert len(misses) == 2 and all(x["matched"] is False for x in misses)
    detail = client.get(f"/api/mock-hits/{misses[0]['id']}", headers=vh)
    assert detail.status_code == 200 and detail.json()["request_body"] == "raw"
    assert client.delete(f"/api/mock-instances/{inst.id}/hits", headers=ah).status_code == 204
    assert client.get(f"/api/mock-instances/{inst.id}/hits", headers=ah).json() == []
    # editor 才能清
    db_session.add(MockHit(instance_id=inst.id, method="GET", path="/x", matched=False))
    db_session.commit()
    assert client.delete(f"/api/mock-instances/{inst.id}/hits", headers=vh).status_code == 403
