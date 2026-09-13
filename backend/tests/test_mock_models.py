"""计划 13 Mock 三表:建行/默认值/端口唯一/JSON 列回读。"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import MockHit, MockInstance, MockRule, MockRuleGroup, Project, User


def _instance(db, project_id, port=19001, **kw):
    inst = MockInstance(project_id=project_id, name="用户服务mock", port=port,
                        token="t" * 32, created_by=None, updated_by=None, **kw)
    db.add(inst)
    db.commit()
    return inst


def test_instance_defaults_and_roundtrip(db_session):
    p = Project(name="p-mock-1")
    db_session.add(p)
    db_session.commit()
    inst = _instance(db_session, p.id)
    assert inst.desired == "stopped"
    assert inst.status == "stopped"
    assert inst.cors_enabled is False
    assert inst.default_status == 404


def test_instance_port_unique(db_session):
    p = Project(name="p-mock-2")
    db_session.add(p)
    db_session.commit()
    _instance(db_session, p.id, port=19002)
    with pytest.raises(IntegrityError):
        _instance(db_session, p.id, port=19002)


def test_rule_defaults_and_conditions_json(db_session):
    p = Project(name="p-mock-3")
    db_session.add(p)
    db_session.commit()
    inst = _instance(db_session, p.id)
    # 计划 15:method/path 上移到组,规则经 group_id 挂组
    group = MockRuleGroup(instance_id=inst.id, method="GET", path_template="/users/{id}")
    db_session.add(group)
    db_session.commit()
    rule = MockRule(instance_id=inst.id, group_id=group.id,
                    conditions=[{"scope": "query", "key": "version", "match": "eq", "value": "2"}])
    db_session.add(rule)
    db_session.commit()
    db_session.refresh(rule)
    assert rule.enabled is True
    assert rule.response_status == 200
    assert rule.conditions[0]["key"] == "version"
    assert rule.sort_order == 0


def test_hit_roundtrip(db_session):
    p = Project(name="p-mock-4")
    db_session.add(p)
    db_session.commit()
    inst = _instance(db_session, p.id)
    hit = MockHit(instance_id=inst.id, rule_id=None, method="POST", path="/x",
                  request_body="hello", matched=False, response_status=404)
    db_session.add(hit)
    db_session.commit()
    db_session.refresh(hit)
    assert hit.matched is False
    assert hit.created_at is not None


# ---------- 计划 15:规则组实体化 + 透传字段 + 命中 outcome/response_body ----------

def _mk_instance(db):
    p = Project(name="p-plan15")
    db.add(p)
    db.flush()
    inst = MockInstance(project_id=p.id, name="t", port=9301, token="tok",
                        created_by=None, updated_by=None)
    db.add(inst)
    db.flush()
    return inst


def test_rule_group_defaults_and_rule_group_fk(db_session):
    """规则组默认值 + 规则经 group_id 挂组(规则自身不再有 method/path)。"""
    inst = _mk_instance(db_session)
    g = MockRuleGroup(instance_id=inst.id, method="GET", path_template="/api/u",
                      description="用户中心", sort_order=0)
    db_session.add(g)
    db_session.flush()
    r = MockRule(instance_id=inst.id, group_id=g.id, conditions=[],
                 response_status=200, response_headers={}, sort_order=0)
    db_session.add(r)
    db_session.commit()
    assert g.enabled is True          # 组默认启用
    assert g.is_deleted is False
    assert r.group_id == g.id
    assert not hasattr(r, "method")   # method/path 上移到组
    assert not hasattr(r, "path_template")


def test_group_passthrough_defaults(db_session):
    """组级透传(2026-09-13 验收调整,由实例级移入):默认关+空;显式赋值可落库。"""
    inst = _mk_instance(db_session)
    g = MockRuleGroup(instance_id=inst.id, method="GET", path_template="/a")
    db_session.add(g)
    db_session.commit()
    assert g.passthrough_enabled is False
    assert g.upstream_base_url is None
    g.passthrough_enabled = True
    g.upstream_base_url = "http://real-api:8080"
    db_session.commit()
    assert g.passthrough_enabled is True


def test_hit_outcome_and_response_body(db_session):
    """命中记录 outcome 默认 fallback;response_body 可落。"""
    inst = _mk_instance(db_session)
    h = MockHit(instance_id=inst.id, method="GET", path="/x", matched=False)
    db_session.add(h)
    db_session.commit()
    assert h.outcome == "fallback"
    assert h.response_body is None
    h.outcome = "forwarded"
    h.response_body = '{"real":true}'
    db_session.commit()
    assert h.response_body == '{"real":true}'
