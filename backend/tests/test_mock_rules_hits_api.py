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


# ---------- 计划 15 T7:四态过滤 + 按组归组过滤 + 响应体出参 ----------

def _hit(db, iid, **kw):
    """直插 MockHit 行(不打真实请求);method/path 可覆盖,其余字段透传。"""
    h = MockHit(instance_id=iid, method=kw.pop("method", "GET"), path=kw.pop("path", "/x"), **kw)
    db.add(h)
    db.commit()
    return h


def test_hits_filter_forwarded_and_unmatched_split(client, db_session, make_user):
    """unmatched 只剩兜底行;forwarded 单列;透传失败落兜底行归 unmatched。

    对 brief 样例的仓内现状对齐(非行为偏离):mock_hits.rule_id 有 FK 到
    mock_rules.id,直插须指向真实规则行,故先建组+规则再引用其 id。
    """
    admin = make_user(db_session, "adm11", is_admin=True)
    inst = _project_inst(db_session, "p-rule-5", 19081)
    group = _group(db_session, inst)
    rule = MockRule(instance_id=inst.id, group_id=group.id)
    db_session.add(rule)
    db_session.commit()
    iid = inst.id
    h_m = _hit(db_session, iid, matched=True, rule_id=rule.id, outcome="matched",
               response_status=200)
    h_f = _hit(db_session, iid, matched=False, outcome="forwarded", response_status=201)
    h_b = _hit(db_session, iid, matched=False, outcome="fallback",
               error="forward-failed: ConnectError", response_status=404)
    ah = _login(client, "adm11")
    fwd = client.get(f"/api/mock-instances/{iid}/hits?filter=forwarded", headers=ah).json()
    assert [x["id"] for x in fwd] == [h_f.id]
    unmatched = client.get(f"/api/mock-instances/{iid}/hits?filter=unmatched", headers=ah).json()
    assert [x["id"] for x in unmatched] == [h_b.id]   # 透传失败行在 unmatched,不在 forwarded
    assert h_m.id not in [x["id"] for x in unmatched]  # 命中行不混入 unmatched


def test_hits_group_filter_attribution(client, db_session, make_user):
    """组过滤:命中行按 rule_id(含软删规则)归组;未命中行按 method+模板匹配归组;他组不串。"""
    admin = make_user(db_session, "adm12", is_admin=True)
    inst = _project_inst(db_session, "p-rule-6", 19082)
    iid = inst.id
    h = _login(client, "adm12")
    g = client.post(f"/api/mock-instances/{iid}/rule-groups",
                    json={"method": "GET", "path_template": "/a/{id}"}, headers=h).json()
    r1 = client.post(f"/api/mock-instances/{iid}/rules",
                     json={"group_id": g["id"], "conditions": [], "response_status": 200},
                     headers=h).json()
    g2 = client.post(f"/api/mock-instances/{iid}/rule-groups",
                     json={"method": "POST", "path_template": "/b"}, headers=h).json()
    r2 = client.post(f"/api/mock-instances/{iid}/rules",
                     json={"group_id": g2["id"], "conditions": [], "response_status": 200},
                     headers=h).json()
    h_hit = _hit(db_session, iid, matched=True, rule_id=r1["id"], outcome="matched", path="/a/1")
    h_unm_in = _hit(db_session, iid, matched=False, outcome="fallback", path="/a/2")
    h_other_m = _hit(db_session, iid, matched=False, outcome="fallback", method="POST", path="/a/3")
    h_other_p = _hit(db_session, iid, matched=False, outcome="fallback", path="/b/9")
    h_hit_g2 = _hit(db_session, iid, matched=True, rule_id=r2["id"], outcome="matched", path="/b")
    assert client.delete(f"/api/mock-rules/{r1['id']}", headers=h).status_code == 204
    ids = [x["id"] for x in
           client.get(f"/api/mock-instances/{iid}/hits?group_id={g['id']}", headers=h).json()]
    # 属G仅两行:h_hit(rule_id 归因,规则软删仍算)+ h_unm_in(未命中但 GET /a/2 命中模板 /a/{id});
    # h_other_m 方法不同、h_other_p 模板不匹配、h_hit_g2 属他组 → 全不出现
    assert ids == [h_unm_in.id, h_hit.id]


def test_hit_detail_response_body(client, db_session, make_user):
    """响应体出参:详情 MockHitDetailOut 带 response_body;列表 MockHitOut 不带。"""
    admin = make_user(db_session, "adm13", is_admin=True)
    inst = _project_inst(db_session, "p-rule-7", 19083)
    group = _group(db_session, inst)
    rule = MockRule(instance_id=inst.id, group_id=group.id)
    db_session.add(rule)
    db_session.commit()
    hit = _hit(db_session, inst.id, matched=True, rule_id=rule.id, outcome="matched",
               response_body='{"x":1}')
    ah = _login(client, "adm13")
    detail = client.get(f"/api/mock-hits/{hit.id}", headers=ah)
    assert detail.status_code == 200 and detail.json()["response_body"] == '{"x":1}'
    listed = client.get(f"/api/mock-instances/{inst.id}/hits", headers=ah).json()
    assert "response_body" not in listed[0] and listed[0]["outcome"] == "matched"


def test_hits_group_filter_rejects_cross_instance_group(client, db_session, make_user):
    """评审修复:group_id 属其它实例(即便同项目)→ 400;否则 A 实例未命中行会按
    B 实例组模板被错归因(查询语义错,非泄漏)。"""
    admin = make_user(db_session, "adm14", is_admin=True)
    p = Project(name="p-rule-8")
    db_session.add(p)
    db_session.commit()
    inst_a = MockInstance(project_id=p.id, name="a", port=19084, token="t" * 32)
    inst_b = MockInstance(project_id=p.id, name="b", port=19085, token="t" * 32)
    db_session.add_all([inst_a, inst_b])
    db_session.commit()
    g_b = _group(db_session, inst_b, method="GET", path="/a/{id}")
    db_session.add(MockHit(instance_id=inst_a.id, method="GET", matched=False,
                           outcome="fallback", path="/a/1"))
    db_session.commit()
    ah = _login(client, "adm14")
    r = client.get(f"/api/mock-instances/{inst_a.id}/hits?group_id={g_b.id}", headers=ah)
    assert r.status_code == 400 and r.json()["detail"] == "group_id 不属于该实例"
