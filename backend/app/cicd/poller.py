"""CI 执行记录轮询器(ADR-0012 决策 3:纯出站轮询):asyncio 后台任务,2s 一轮。

对 queued/running 且 build_number 非空的执行记录:查 build 状态 → 拉 progressiveText 增量
(落盘 + 总线直播)→ 终态拉产物解析落库。异常一律吞掉不炸平台(mock 探活同款纪律);
后端重启后轮询自然续跑(状态在库里,无需额外对账)——这就是对账。
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from app.cicd import jenkins_client, junit_parse
from app.config import settings
from app.jobs.bus import bus

_POLL_INTERVAL = 2.0
_VERDICT = {"SUCCESS": "success", "FAILURE": "failure", "UNSTABLE": "failure", "ABORTED": "aborted"}

_task: asyncio.Task | None = None


def start_poll_task() -> None:
    global _task
    if _task is None:
        _task = asyncio.create_task(_poll_loop())


def stop_poll_task() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None


async def _poll_loop() -> None:
    while True:
        try:
            await _poll_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(_POLL_INTERVAL)


async def _poll_once(client: jenkins_client.JenkinsClient | None = None) -> None:
    # 单轮全是同步 HTTP/DB 调用,挪进工作线程执行,避免 Jenkins 慢/不可达时冻住事件循环
    await asyncio.to_thread(_poll_round, client)


def _poll_round(client: jenkins_client.JenkinsClient | None = None) -> None:
    from app.database import SessionLocal
    from app.models import CiRun, JenkinsConnection

    with SessionLocal() as db:
        rows = db.query(CiRun).filter(CiRun.status.in_(("queued", "running")),
                                      CiRun.build_number.isnot(None)).all()
        if not rows:
            return
        conn = db.query(JenkinsConnection).first()
        if conn is None:
            return
        own = client or jenkins_client.JenkinsClient(conn.base_url, conn.api_user, conn.api_token)
        try:
            for run in rows:
                try:
                    _poll_run(db, own, run)
                except jenkins_client.JenkinsError:
                    raise
                except Exception:
                    continue  # 单行异常不拖垮整轮
        finally:
            if client is None:  # 测试注入的客户端由其所有者关闭
                own.close()


def _emit(run: CiRun, event: dict) -> None:
    bus.publish_nowait(f"ci_{run.id}", event)


def _append_log(run: CiRun, chunk: str, new_offset: int) -> None:
    d = settings.ci_data_dir / "runs" / str(run.id)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "console.log", "a", encoding="utf-8") as f:
        f.write(chunk)
    run.console_bytes = new_offset
    _emit(run, {"type": "log", "text": chunk})


def _poll_run(db, client: jenkins_client.JenkinsClient, run: CiRun) -> None:
    build = client.get_build(run.jenkins_job, run.build_number)
    if build is None:
        run.status = "error"
        run.error = "Jenkins 侧构建不存在(可能已被删除)"
        run.finished_at = datetime.now()
        db.commit()
        _emit(run, {"type": "done", "status": "error"})
        return
    if run.status == "queued" and build["building"]:
        run.status = "running"
        run.started_at = datetime.now()
        db.commit()
        _emit(run, {"type": "status", "status": "running"})
    chunk, new_offset = client.read_console_chunk(run.jenkins_job, run.build_number,
                                                  run.console_bytes)
    if chunk:
        _append_log(run, chunk, new_offset)
        db.commit()
    if not build["building"]:
        _finalize(db, client, run, build["result"] or "ABORTED")


def _finalize(db, client: jenkins_client.JenkinsClient, run: CiRun, result: str) -> None:
    run.status = _VERDICT.get(result, "error")
    run.finished_at = datetime.now()
    if run.status in ("success", "failure"):
        cases: list[dict] = []
        try:
            for rel in client.list_artifacts(run.jenkins_job, run.build_number):
                if not rel.endswith(".xml"):
                    continue
                if "ci-results/" not in rel and "surefire-reports/" not in rel:
                    continue
                blob = client.get_artifact(run.jenkins_job, run.build_number, rel)
                cases.extend(junit_parse.parse_junit_xml(blob.decode("utf-8", "replace")))
        except jenkins_client.JenkinsError:
            pass  # 产物拉不到:报告为空,构建结论仍以 Jenkins result 为准
        run.results = cases
        run.total = len(cases)
        run.passed = sum(1 for c in cases if c["status"] == "passed")
        run.failed = sum(1 for c in cases if c["status"] == "failed")
        run.skipped = sum(1 for c in cases if c["status"] == "skipped")
    db.commit()
    _emit(run, {"type": "done", "status": run.status})
