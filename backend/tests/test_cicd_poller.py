"""计划 16 Task 11:轮询器三段——运行中(状态+日志增量)/终态(产物解析)/构建消失。"""
import asyncio
import httpx

from app.cicd import poller
from app.cicd.jenkins_client import JenkinsClient
from app.config import settings
from app.jobs.bus import bus
from app.models import CiRun, ExecutionPlan, JenkinsConnection, Project
from tests.test_cicd_jenkins_client import FakeJenkins

SUREFIRE = """<testsuite name="com.x.AuthApiTest" time="0.5">
  <testcase name="loginOk" classname="com.x.AuthApiTest" time="0.1"/>
  <testcase name="loginBad" classname="com.x.AuthApiTest" time="0.2">
    <failure message="404">assert</failure>
  </testcase>
</testsuite>"""


def _mk_run(db, run_id: int) -> CiRun:
    # 测试库启用真实 FK:先建父行(Project/ExecutionPlan)并落库,再挂 CiRun
    db.add(JenkinsConnection(id=1, base_url="http://jk", api_user="a", api_token="t"))
    db.add(Project(id=1, name="poller-p"))
    db.commit()
    db.add(ExecutionPlan(id=1, project_id=1, name="p", kind="api", branch="master", selection=[]))
    db.commit()
    run = CiRun(id=run_id, project_id=1, plan_id=1, plan_name="p", kind="api",
                branch="master", selection=[], status="queued", jenkins_job="j1",
                build_number=1, jenkins_url="http://jk/job/j1/1/")
    db.add(run)
    db.commit()
    return run


def test_running_chunk_appends_log_and_status(db_session):
    fk = FakeJenkins()
    fk.jobs.add("j1")
    fk.builds[("j1", 1)] = {"building": True, "result": None, "url": "http://jk/job/j1/1/"}
    fk.logs[("j1", 1)] = "第一行日志\n第二行\n".encode()
    run = _mk_run(db_session, 501)
    events = []
    q = bus.subscribe("ci_501")

    async def drain():
        # 单轮轮询:queued→running + 日志增量
        await poller._poll_once(client=fk.client())
        while not q.empty():
            events.append(q.get_nowait())

    asyncio.run(drain())
    db_session.refresh(run)
    assert run.status == "running" and run.started_at is not None
    assert run.console_bytes == len("第一行日志\n第二行\n".encode())
    log_file = settings.ci_data_dir / "runs" / "501" / "console.log"
    assert "第二行" in log_file.read_text(encoding="utf-8")
    types = [e["type"] for e in events]
    assert "status" in types and "log" in types and "done" not in types
    bus.unsubscribe("ci_501", q)


def test_finalize_parses_artifacts(db_session):
    fk = FakeJenkins()
    fk.jobs.add("j1")
    fk.builds[("j1", 1)] = {"building": False, "result": "SUCCESS", "url": "http://jk/job/j1/1/"}
    fk.artifacts[("j1", 1)] = {"surefire-reports/com.x.AuthApiTest.xml": SUREFIRE.encode()}
    run = _mk_run(db_session, 502)
    run.status = "running"  # 从 running 进入终态
    run.console_bytes = 10
    db_session.commit()
    q = bus.subscribe("ci_502")

    async def drain():
        await poller._poll_once(client=fk.client())

    asyncio.run(drain())
    db_session.refresh(run)
    assert run.status == "success"
    assert (run.total, run.passed, run.failed, run.skipped) == (2, 1, 1, 0)
    assert run.results[1]["name"] == "loginBad" and run.results[1]["message"] == "404"
    assert run.finished_at is not None
    assert q.get_nowait()["type"] == "done"
    bus.unsubscribe("ci_502", q)


def test_missing_build_marks_error(db_session):
    fk = FakeJenkins()  # 无 j1/任何 build → 404
    run = _mk_run(db_session, 503)

    async def drain():
        await poller._poll_once(client=fk.client())

    asyncio.run(drain())
    db_session.refresh(run)
    assert run.status == "error" and run.error and "不存在" in run.error
