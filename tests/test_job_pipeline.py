# tests/test_job_pipeline.py
import json

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Document, GenerationJob, Module, Project, StagedCase


def _admin_headers(client, db_session):
    """Task 7 补鉴权:bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。
    原断言语义不变,仅补鉴权头。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _seed(db, storage_path):
    p = Project(name="管道测试项目")
    db.add(p)
    db.flush()
    m = Module(project_id=p.id, name="登录模块")
    db.add(m)
    db.flush()
    d = Document(project_id=p.id, filename="需求.md", storage_path=storage_path)
    db.add(d)
    db.commit()
    return p, m, d


CASE_RESULT = {"feature_points": [{"name": "账号登录", "cases": [
    {"title": "登录成功", "priority": "P0", "precondition": "已注册", "remark": None,
     "steps": [{"action": "输入", "expected": "成功"}]}
]}]}


async def _fake_engine_ok(*args, **kwargs):
    yield ("thinking", "先看技能方法论…")
    yield ("delta", "我先解析文档,再按功能点归组。")
    yield ("tool", "Skill functional-testing")
    yield ("tool", "Read .claude/skills/functional-testing/prompts/functional-testing.md")
    yield ("usage", (100, 50, 0.42))
    yield ("result", CASE_RESULT)


async def test_process_job_success(monkeypatch, tmp_path):
    import app.jobs.pipeline as pl
    from app.jobs.bus import bus

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 登录需求\n输入账号密码后登录成功。", encoding="utf-8")

    monkeypatch.setattr(pl, "stream_skill_generation", _fake_engine_ok)
    db = SessionLocal()
    try:
        p, m, d = _seed(db, str(doc_file))
        job = GenerationJob(project_id=p.id, document_id=d.id, target_module_id=m.id)
        db.add(job)
        db.commit()
        q = bus.subscribe(job.id)
        await pl.process_job(job.id)
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        db.refresh(job)
        assert job.status == "completed"
        assert job.input_tokens == 100 and job.output_tokens == 50
        assert job.cost_usd == 0.42  # 费用来自 SDK total_cost_usd
        # 过程记录落库
        assert job.tool_trace == (
            "Skill functional-testing\n"
            "Read .claude/skills/functional-testing/prompts/functional-testing.md\n"
        )
        # SSE 侧:tool 事件逐条推送
        tool_events = [e for e in events if e["type"] == "tool"]
        assert len(tool_events) == 2
        assert tool_events[0]["text"] == "Skill functional-testing\n"
        staged = db.query(StagedCase).filter(StagedCase.job_id == job.id).all()
        assert len(staged) == 1
        assert staged[0].feature_point_name == "账号登录"
        assert staged[0].steps[0]["action"] == "输入"
        assert any(e["type"] == "status" and e["status"] == "running" for e in events)
        delta_events = [e for e in events if e["type"] == "delta"]
        assert len(delta_events) == 1
        assert delta_events[0]["text"] == "我先解析文档,再按功能点归组。"
        assert any(e["type"] == "done" and e["staged_count"] == 1 for e in events)
    finally:
        db.close()


async def test_process_job_failure_sets_failed(monkeypatch, tmp_path):
    import app.jobs.pipeline as pl
    from app.jobs.bus import bus

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 需求", encoding="utf-8")

    async def boom(*a, **k):
        raise RuntimeError("api down")
        yield  # pragma: no cover

    monkeypatch.setattr(pl, "stream_skill_generation", boom)
    db = SessionLocal()
    try:
        p, m, d = _seed(db, str(doc_file))
        job = GenerationJob(project_id=p.id, document_id=d.id, target_module_id=m.id)
        db.add(job)
        db.commit()
        q = bus.subscribe(job.id)
        await pl.process_job(job.id)  # 不重抛
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        db.refresh(job)
        assert job.status == "failed"
        assert "api down" in job.error
        assert any(e["type"] == "error" and "api down" in e["message"] for e in events)
    finally:
        db.close()


def test_create_job_endpoint_and_validation(client, db_session):
    ah = _admin_headers(client, db_session)
    pid = client.post("/api/projects", json={"name": "任务API项目"}, headers=ah).json()["id"]
    doc = client.post(f"/api/projects/{pid}/documents", files={"file": ("r.md", "# 需求".encode("utf-8"), "text/markdown")}, headers=ah).json()
    mod = client.post(f"/api/projects/{pid}/modules", json={"name": "模块"}, headers=ah).json()
    resp = client.post(f"/api/projects/{pid}/jobs", json={"document_id": doc["id"], "target_module_id": mod["id"]}, headers=ah)
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["model"] == "claude-opus-5"
    other = client.post("/api/projects", json={"name": "另一项目"}, headers=ah).json()["id"]
    bad = client.post(f"/api/projects/{other}/jobs", json={"document_id": doc["id"], "target_module_id": mod["id"]}, headers=ah)
    assert bad.status_code == 400
    listing = client.get(f"/api/projects/{pid}/jobs", headers=ah)
    assert listing.status_code == 200 and any(j["id"] == body["id"] for j in listing.json())
    detail = client.get(f"/api/jobs/{body['id']}", headers=ah)
    assert detail.status_code == 200 and detail.json()["status"] == "pending"


async def _fake_stream_garbage_then_usage(*a, **kw):
    yield ("delta", "不是合法 JSON")
    yield ("usage", (150, 250, 2.5))


async def test_case_job_persists_stream_text_and_times(monkeypatch, tmp_path):
    """A1+A2:delta 全部落 output_text;completed 后 started/finished 均非空且有序。"""
    import app.jobs.pipeline as pl

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 登录需求\n输入账号密码后登录成功。", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_skill_generation", _fake_engine_ok)
    db = SessionLocal()
    try:
        p, m, d = _seed(db, str(doc_file))
        job = GenerationJob(project_id=p.id, document_id=d.id, target_module_id=m.id)
        db.add(job)
        db.commit()
        await pl.process_job(job.id)
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.status == "completed"
        assert "我先解析文档,再按功能点归组。" in got.output_text
        assert "===== 产物 JSON =====" in got.output_text
        assert '"feature_points"' in got.output_text  # 结构化产物追加进回放文本
        assert got.tool_trace is not None
        assert got.started_at is not None and got.finished_at is not None
        assert got.started_at <= got.finished_at
    finally:
        db.close()


async def test_case_job_tokens_survive_parse_failure(monkeypatch, tmp_path):
    """A3 核心:AI 流已消耗 tokens,随后解析抛异常 → tokens/cost 必须已落库;失败也写终态时间。"""
    import app.jobs.pipeline as pl

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 需求", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_skill_generation", _fake_stream_garbage_then_usage)
    db = SessionLocal()
    try:
        p, m, d = _seed(db, str(doc_file))
        job = GenerationJob(project_id=p.id, document_id=d.id, target_module_id=m.id)
        db.add(job)
        db.commit()
        await pl.process_job(job.id)
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.status == "failed"
        assert got.input_tokens == 150 and got.output_tokens == 250
        assert got.cost_usd == 2.5
        assert got.finished_at is not None
        assert got.output_text == "不是合法 JSON"  # 异常路径 flush 已写部分
    finally:
        db.close()


async def test_case_job_persists_thinking_text(monkeypatch, tmp_path):
    """计划6:思考摘要随流落库,completed 后 thinking_text 为思考全文。"""
    import app.jobs.pipeline as pl

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 登录需求\n", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_skill_generation", _fake_engine_ok)
    db = SessionLocal()
    try:
        p, m, d = _seed(db, str(doc_file))
        job = GenerationJob(project_id=p.id, document_id=d.id, target_module_id=m.id)
        db.add(job)
        db.commit()
        await pl.process_job(job.id)
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.status == "completed"
        assert got.thinking_text == "先看技能方法论…"
        assert got.output_text is not None and '"feature_points"' in got.output_text
    finally:
        db.close()


async def test_case_job_thinking_survives_parse_failure(monkeypatch, tmp_path):
    """计划6:思考先于产物流到达,解析抛异常时 thinking_text 也必须已落库(与 A3 同理)。"""
    import app.jobs.pipeline as pl

    async def garbage_with_thinking(*a, **kw):
        yield ("thinking", "思考中…")
        yield ("delta", "不是合法 JSON")
        yield ("usage", (150, 250, 2.5))

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 需求", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_skill_generation", garbage_with_thinking)
    db = SessionLocal()
    try:
        p, m, d = _seed(db, str(doc_file))
        job = GenerationJob(project_id=p.id, document_id=d.id, target_module_id=m.id)
        db.add(job)
        db.commit()
        await pl.process_job(job.id)
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.status == "failed"
        assert got.thinking_text == "思考中…"
    finally:
        db.close()


async def test_stream_threshold_flush_mid_stream(monkeypatch, tmp_path):
    """计划6收尾:超阈值(STREAM_FLUSH_THRESHOLD=4096)的 thinking/output 在流中途中途即落库,不等终态。"""
    from sqlalchemy import text as sql_text
    import app.jobs.pipeline as pl

    probe = {}
    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 需求", encoding="utf-8")

    async def big_then_probe(*a, **kw):
        yield ("thinking", "T" * 5000)
        yield ("delta", "X" * 5000)
        # 生成器恢复时探查 DB:此时 process_job 已处理完上述两个大块并 flush
        pdb = SessionLocal()
        try:
            row = pdb.execute(
                sql_text("SELECT CHAR_LENGTH(thinking_text) AS t, CHAR_LENGTH(output_text) AS o FROM generation_jobs WHERE id = :i"),
                {"i": job.id},
            ).one()
            probe["t"], probe["o"] = row[0], row[1]
        finally:
            pdb.close()
        yield ("usage", (10, 10, 1.0))

    monkeypatch.setattr(pl, "stream_skill_generation", big_then_probe)
    db = SessionLocal()
    try:
        p, m, d = _seed(db, str(doc_file))
        job = GenerationJob(project_id=p.id, document_id=d.id, target_module_id=m.id)
        db.add(job)
        db.commit()
        await pl.process_job(job.id)
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.status == "failed"  # "X"*5000 不是合法 JSON → 解析失败
        assert probe["t"] >= 5000, f"thinking_text mid-stream flush: expected >=5000, got {probe['t']}"
        assert probe["o"] >= 5000, f"output_text mid-stream flush: expected >=5000, got {probe['o']}"
        assert len(got.thinking_text) >= 5000
        assert len(got.output_text) >= 5000
    finally:
        db.close()


def test_sse_endpoint_snapshot_and_404(client, db_session):
    ah = _admin_headers(client, db_session)
    assert client.get("/api/jobs/999999/events", headers=ah).status_code == 404
    db = SessionLocal()
    try:
        p = Project(name="SSE项目")
        db.add(p)
        db.flush()
        job = GenerationJob(
            project_id=p.id, document_id=None, target_module_id=None, status="completed",
            output_text="历史任务流式输出", input_tokens=11, output_tokens=22,
            thinking_text="历史思考摘要全文",
            tool_trace="Read a.java\n",
            artifacts=[{"path": "a.java", "action": "created"}, {"path": "b.java", "action": "overwritten"}],
        )
        db.add(job)
        db.commit()
        jid = job.id
    finally:
        db.close()
    with client.stream("GET", f"/api/jobs/{jid}/events", headers=ah) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        lines = [ln for ln in r.iter_lines() if ln.strip()]
    assert len(lines) == 2  # 终态:status 快照 + 完整 snapshot 后关流
    assert json.loads(lines[0][len("data: "):]) == {"type": "status", "status": "completed"}
    snap = json.loads(lines[1][len("data: "):])
    assert snap["type"] == "snapshot"
    assert snap["status"] == "completed" and snap["error"] is None
    assert snap["output_text"] == "历史任务流式输出"
    assert snap["thinking_text"] == "历史思考摘要全文"
    assert snap["input_tokens"] == 11 and snap["output_tokens"] == 22
    assert snap["files_count"] == 2 and snap["staged_count"] == 0
    assert snap["tool_trace"] == "Read a.java\n"


async def test_case_job_fallback_parses_narration(monkeypatch, tmp_path):
    """SDK result 缺失(理论上不该发生)→ 解析层兜底:叙述文本里的裸 JSON 仍可入库。"""
    import app.jobs.pipeline as pl

    async def narration_only(*a, **kw):
        yield ("delta", '{"feature_points": [{"name": "登录", "cases": [')
        yield ("delta", '{"title": "登录成功", "priority": "P0", "steps": [{"action": "输入", "expected": "成功"}]}]}]}')
        yield ("usage", (100, 50, 0.5))

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 需求", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_skill_generation", narration_only)
    db = SessionLocal()
    try:
        p, m, d = _seed(db, str(doc_file))
        job = GenerationJob(project_id=p.id, document_id=d.id, target_module_id=m.id)
        db.add(job)
        db.commit()
        await pl.process_job(job.id)
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.status == "completed"
        staged = db.query(StagedCase).filter(StagedCase.job_id == job.id).count()
        assert staged == 1
        assert "===== 产物 JSON =====" not in got.output_text  # 无 result 不追加分隔标记
    finally:
        db.close()


async def test_case_job_passes_user_prompt_to_engine(monkeypatch, tmp_path):
    """补充提示词随任务持久化并进入引擎提示词。"""
    import app.jobs.pipeline as pl

    captured = {}

    async def capture_prompt(*a, **kw):
        captured["prompt"] = kw.get("prompt") or (a[0] if a else "")
        yield ("usage", (1, 1, 0.0))
        yield ("result", CASE_RESULT)

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 需求", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_skill_generation", capture_prompt)
    db = SessionLocal()
    try:
        p, m, d = _seed(db, str(doc_file))
        job = GenerationJob(project_id=p.id, document_id=d.id, target_module_id=m.id,
                            user_prompt="只测登录")
        db.add(job)
        db.commit()
        await pl.process_job(job.id)
        assert "只测登录" in captured["prompt"]
        assert "# 补充指令" in captured["prompt"]
        assert "functional-testing" in captured["prompt"]  # 技能调度指令在提示词内
    finally:
        db.close()
