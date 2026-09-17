"""计划 16 Task 1:CI/CD 四张新表的存在性、唯一约束与默认值。"""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import CiRun, ExecutionPlan, InterfaceCase, JenkinsConnection, Project


def _mk_project(db, name="cicd域项目"):
    # F2 裁定:create_all 建的是真 FK,先建父行再用真实 id(断言不变)
    p = Project(name=name)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def test_execution_plan_roundtrip(db_session):
    proj = _mk_project(db_session)
    p = ExecutionPlan(project_id=proj.id, name="冒烟回归", kind="api", branch="master",
                      selection=[{"ref": "com.x.A#m1", "class_name": "com.x.A", "method": "m1"}])
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    assert p.id > 0 and p.is_deleted is False and p.selection[0]["method"] == "m1"


def test_interface_case_unique_per_branch(db_session):
    proj = _mk_project(db_session, name="cicd接口用例项目")
    kwargs = dict(project_id=proj.id, branch="master", class_name="com.x.A", method="m1")
    db_session.add(InterfaceCase(**kwargs))
    db_session.commit()
    db_session.add(InterfaceCase(**kwargs))  # 同 仓×分支×类×方法 重复 → 违反唯一约束
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_ci_run_defaults(db_session):
    proj = _mk_project(db_session, name="cicd执行记录项目")
    plan = ExecutionPlan(project_id=proj.id, name="x", kind="ui", branch="master")
    db_session.add(plan)
    db_session.commit()
    db_session.refresh(plan)
    r = CiRun(project_id=proj.id, plan_id=plan.id, plan_name="x", kind="ui", branch="master",
              jenkins_job="light_tester_p1_ui")
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    assert r.status == "queued" and r.build_number is None
    assert r.total == 0 and r.console_bytes == 0


def test_jenkins_connection_singleton(db_session):
    db_session.add(JenkinsConnection(id=1, base_url="http://localhost:8081",
                                     api_user="admin", api_token="t"))
    db_session.commit()
    db_session.add(JenkinsConnection(id=1, base_url="x", api_user="y", api_token="z"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_interface_case_web_columns(db_session):
    """计划 17:注册表扩列承载 web 域(case_type/title/markers),api 行默认值不变。"""
    from app.models import InterfaceCase, Project

    db_session.add(Project(id=99, name="plan17"))
    db_session.commit()
    row = InterfaceCase(project_id=99, branch="main", class_name="tests/test_smoke.py",
                        method="test_a", status="active", framework="pytest",
                        case_type="web", title="链路 1:登录态缓存", markers=["account:standard"])
    db_session.add(row)
    db_session.commit()
    db_session.expire_all()
    got = db_session.get(InterfaceCase, row.id)
    assert got.case_type == "web" and got.title == "链路 1:登录态缓存"
    assert got.markers == ["account:standard"]
    # api 侧缺省:不传即 'api'/None/[]
    api_row = InterfaceCase(project_id=99, branch="main", class_name="com.x.A", method="m")
    db_session.add(api_row)
    db_session.commit()
    db_session.expire_all()
    got = db_session.get(InterfaceCase, api_row.id)
    assert got.case_type == "api" and got.title is None and (got.markers or []) == []
