"""计划 13 Mock 三表:建行/默认值/端口唯一/JSON 列回读。"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import MockHit, MockInstance, MockRule, Project, User


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
    rule = MockRule(instance_id=inst.id, method="GET", path_template="/users/{id}",
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
