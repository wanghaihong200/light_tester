# tests/test_job_pipeline.py
import json

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import Document, GenerationJob, Module, Project, StagedCase


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


async def _fake_stream_ok(project_name, module_name, doc_content):
    yield ("delta", '{"feature_points": [{"name": "账号登录", "cases": [')
    yield ("delta", '{"title": "登录成功", "priority": "P0", "precondition": "已注册", "remark": null, "steps": [{"action": "输入", "expected": "成功"}]}]}]}')
    yield ("usage", (100, 50))


async def test_process_job_success(monkeypatch, tmp_path):
    import app.jobs.pipeline as pl
    from app.jobs.bus import bus

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 登录需求\n输入账号密码后登录成功。", encoding="utf-8")

    monkeypatch.setattr(pl, "stream_case_generation", _fake_stream_ok)
    monkeypatch.setattr(pl, "estimate_cost", lambda m, i, o: 1.5)
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
        assert job.cost_usd == 1.5
        staged = db.query(StagedCase).filter(StagedCase.job_id == job.id).all()
        assert len(staged) == 1
        assert staged[0].feature_point_name == "账号登录"
        assert staged[0].steps[0]["action"] == "输入"
        assert any(e["type"] == "status" and e["status"] == "running" for e in events)
        # delta 事件必须携带 text 载荷(与 _fake_stream_ok 的第一个 delta 对齐)
        delta_events = [e for e in events if e["type"] == "delta"]
        assert len(delta_events) == 2
        assert delta_events[0]["text"] == '{"feature_points": [{"name": "账号登录", "cases": ['
        assert delta_events[1]["text"] == '{"title": "登录成功", "priority": "P0", "precondition": "已注册", "remark": null, "steps": [{"action": "输入", "expected": "成功"}]}]}]}'
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

    monkeypatch.setattr(pl, "stream_case_generation", boom)
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


def test_create_job_endpoint_and_validation(client):
    pid = client.post("/api/projects", json={"name": "任务API项目"}).json()["id"]
    doc = client.post(f"/api/projects/{pid}/documents", files={"file": ("r.md", "# 需求".encode("utf-8"), "text/markdown")}).json()
    mod = client.post(f"/api/projects/{pid}/modules", json={"name": "模块"}).json()
    resp = client.post(f"/api/projects/{pid}/jobs", json={"document_id": doc["id"], "target_module_id": mod["id"]})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["model"] == "claude-opus-5"
    other = client.post("/api/projects", json={"name": "另一项目"}).json()["id"]
    bad = client.post(f"/api/projects/{other}/jobs", json={"document_id": doc["id"], "target_module_id": mod["id"]})
    assert bad.status_code == 400
    listing = client.get(f"/api/projects/{pid}/jobs")
    assert listing.status_code == 200 and any(j["id"] == body["id"] for j in listing.json())
    detail = client.get(f"/api/jobs/{body['id']}")
    assert detail.status_code == 200 and detail.json()["status"] == "pending"


async def _fake_stream_valid_long(project_name, module_name, doc_content):
    yield ("delta", '{"feature_points": [{"name": "账号登录", "cases": [')
    yield ("delta", '{"title": "登录成功", "priority": "P0", "precondition": null, "remark": null, "steps": [{"action": "输入", "expected": "成功"}]}]}]}')
    yield ("usage", (100, 50))


async def _fake_stream_garbage_then_usage(project_name, module_name, doc_content):
    yield ("delta", "不是合法 JSON")
    yield ("usage", (150, 250))


async def test_case_job_persists_stream_text_and_times(monkeypatch, tmp_path):
    """A1+A2:delta 全部落 output_text;completed 后 started/finished 均非空且有序。"""
    import app.jobs.pipeline as pl

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 登录需求\n输入账号密码后登录成功。", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_case_generation", _fake_stream_valid_long)
    monkeypatch.setattr(pl, "estimate_cost", lambda m, i, o: 1.5)
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
        assert got.output_text == (
            '{"feature_points": [{"name": "账号登录", "cases": ['
            '{"title": "登录成功", "priority": "P0", "precondition": null, "remark": null, "steps": [{"action": "输入", "expected": "成功"}]}]}]}'
        )
        assert got.started_at is not None and got.finished_at is not None
        assert got.started_at <= got.finished_at
    finally:
        db.close()


async def test_case_job_tokens_survive_parse_failure(monkeypatch, tmp_path):
    """A3 核心:AI 流已消耗 tokens,随后解析抛异常 → tokens/cost 必须已落库;失败也写终态时间。"""
    import app.jobs.pipeline as pl

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 需求", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_case_generation", _fake_stream_garbage_then_usage)
    monkeypatch.setattr(pl, "estimate_cost", lambda m, i, o: 2.5)
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


async def _fake_stream_with_thinking(project_name, module_name, doc_content):
    yield ("thinking", "分析:文档含登录需求,拆为功能点…")
    yield ("delta", '{"feature_points": [{"name": "登录", "cases": [')
    yield ("delta", '{"title": "登录成功", "priority": "P0", "steps": [{"action": "输入", "expected": "成功"}]}]}]}')
    yield ("usage", (100, 50))


async def test_case_job_persists_thinking_text(monkeypatch, tmp_path):
    """计划6:思考摘要随流落库,completed 后 thinking_text 为思考全文。"""
    import app.jobs.pipeline as pl

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 登录需求\n", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_case_generation", _fake_stream_with_thinking)
    monkeypatch.setattr(pl, "estimate_cost", lambda m, i, o: 1.5)
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
        assert got.thinking_text == "分析:文档含登录需求,拆为功能点…"
        assert got.output_text is not None and '"feature_points"' in got.output_text
    finally:
        db.close()


async def test_case_job_thinking_survives_parse_failure(monkeypatch, tmp_path):
    """计划6:思考先于产物流到达,解析抛异常时 thinking_text 也必须已落库(与 A3 同理)。"""
    import app.jobs.pipeline as pl

    async def garbage_with_thinking(project_name, module_name, doc_content):
        yield ("thinking", "思考中…")
        yield ("delta", "不是合法 JSON")
        yield ("usage", (150, 250))

    doc_file = tmp_path / "需求.md"
    doc_file.write_text("# 需求", encoding="utf-8")
    monkeypatch.setattr(pl, "stream_case_generation", garbage_with_thinking)
    monkeypatch.setattr(pl, "estimate_cost", lambda m, i, o: 2.5)
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


def test_sse_endpoint_snapshot_and_404(client):
    assert client.get("/api/jobs/999999/events").status_code == 404
    db = SessionLocal()
    try:
        p = Project(name="SSE项目")
        db.add(p)
        db.flush()
        job = GenerationJob(
            project_id=p.id, document_id=None, target_module_id=None, status="completed",
            output_text="历史任务流式输出", input_tokens=11, output_tokens=22,
            artifacts=[{"path": "a.java", "action": "created"}, {"path": "b.java", "action": "overwritten"}],
        )
        db.add(job)
        db.commit()
        jid = job.id
    finally:
        db.close()
    with client.stream("GET", f"/api/jobs/{jid}/events") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        lines = [ln for ln in r.iter_lines() if ln.strip()]
    assert len(lines) == 2  # 终态:status 快照 + 完整 snapshot 后关流
    assert json.loads(lines[0][len("data: "):]) == {"type": "status", "status": "completed"}
    snap = json.loads(lines[1][len("data: "):])
    assert snap["type"] == "snapshot"
    assert snap["status"] == "completed" and snap["error"] is None
    assert snap["output_text"] == "历史任务流式输出"
    assert snap["input_tokens"] == 11 and snap["output_tokens"] == 22
    assert snap["files_count"] == 2 and snap["staged_count"] == 0
