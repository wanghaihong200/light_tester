# tests/test_api_gen_handler.py
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import app.jobs.api_gen as ag
from app.database import SessionLocal
from app.jobs import api_gen
from app.jobs.api_gen import ApiFilesPayload, MvnResult, parse_api_files, write_files, run_mvn_compile, collect_project_summary
from app.models import Document, GenerationJob, Project

_EMPTY_SUMMARY = {"group_id": None, "artifact_id": None, "has_rest_assured": True,
                  "has_junit5": True, "has_hamcrest": False, "test_packages": [], "has_base_class": False}


def _seed_api_job(db, storage_path):
    p = Project(name="api任务测试项目", git_repo_url="http://x/repo.git")
    db.add(p)
    db.flush()
    d = Document(project_id=p.id, filename="api.md", storage_path=storage_path)
    db.add(d)
    db.commit()
    job = GenerationJob(project_id=p.id, document_id=d.id, job_type="api_generation")
    db.add(job)
    db.commit()
    return job


def test_parse_api_files_strips_fence_and_validates():
    text = '```json\n{"files":[{"path":"src/test/java/T.java","content":"class T{}"}]}'  + '```'
    p = parse_api_files(text)
    assert len(p.files) == 1
    assert p.files[0].path == "src/test/java/T.java"


def test_parse_api_files_wraps_top_level_array():
    """E2E 实测:模型会输出顶层数组 + 围栏(结构化输出端点不强制 schema),解析层归一化。

    与 pipeline._parse_staged_payload 的顶层数组归一化同构(计划 3 的既有教训)。
    """
    text = '```json\n[{"path":"src/test/java/T.java","content":"class T{}"},{"path":"src/test/resources/test.properties","content":"k=v"}]\n```'
    p = parse_api_files(text)
    assert len(p.files) == 2
    assert p.files[0].path == "src/test/java/T.java"


def test_write_files_rejects_traversal(tmp_path):
    with pytest.raises(Exception):
        write_files(tmp_path, [{"path": "../x.java", "content": "x"}])


def test_write_files_rejects_tracked_overwrite(tmp_path):
    # 造一个 git 仓库,T.java 已跟踪
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "T.java").write_text("old", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)
    with pytest.raises(Exception) as e:
        write_files(tmp_path, [{"path": "T.java", "content": "new"}])
    assert "T.java" in str(e.value)


def test_write_files_creates_untracked(tmp_path):
    result = write_files(tmp_path, [{"path": "src/test/java/T.java", "content": "class T{}"}])
    assert result == [{"path": "src/test/java/T.java", "action": "created"}]
    assert (tmp_path / "src/test/java/T.java").read_text(encoding="utf-8") == "class T{}"


def test_run_mvn_compile_success(tmp_path, monkeypatch):
    def fake_run(args, **kw):
        return subprocess.CompletedProcess(args, 0, b"", b"")
    monkeypatch.setattr(api_gen.subprocess, "run", fake_run)
    r = run_mvn_compile(tmp_path)
    assert r.success is True


def test_run_mvn_compile_failure_returns_output(tmp_path, monkeypatch):
    def fake_run(args, **kw):
        return subprocess.CompletedProcess(args, 1, "BUILD FAILURE\n错误行".encode("utf-8"), b"")
    monkeypatch.setattr(api_gen.subprocess, "run", fake_run)
    r = run_mvn_compile(tmp_path)
    assert r.success is False
    assert "错误行" in r.output


def test_collect_project_summary_with_pom(tmp_path):
    (tmp_path / "pom.xml").write_text("""<project>
      <groupId>com.example</groupId>
      <artifactId>order-api</artifactId>
      <dependencies>
        <dependency><artifactId>rest-assured</artifactId></dependency>
        <dependency><artifactId>junit-jupiter</artifactId></dependency>
      </dependencies>
    </project>""", encoding="utf-8")
    (tmp_path / "src/test/java/com/example/api").mkdir(parents=True)
    (tmp_path / "src/test/java/com/example/api/BaseApiTest.java").write_text("x", encoding="utf-8")
    s = collect_project_summary(tmp_path)
    assert s["group_id"] == "com.example"
    assert s["artifact_id"] == "order-api"
    assert s["has_rest_assured"] is True
    assert s["has_junit5"] is True
    assert "com.example.api" in s["test_packages"]
    assert s["has_base_class"] is True


def test_run_mvn_compile_resolves_mvn_via_which(tmp_path, monkeypatch):
    """回归(2026-08-17 E2E 实测):Windows 下 mvn 是 .cmd,subprocess 直调 "mvn" 找不到。
    必须用 shutil.which 解析全路径。"""
    seen = {}

    def fake_run(args, **kw):
        seen["argv0"] = args[0]
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(api_gen.shutil, "which", lambda name: "C:/tools/mvn.cmd")
    monkeypatch.setattr(api_gen.subprocess, "run", fake_run)
    r = run_mvn_compile(tmp_path)
    assert r.success is True
    assert seen["argv0"] == "C:/tools/mvn.cmd"


def test_run_mvn_compile_mvn_not_on_path(tmp_path, monkeypatch):
    monkeypatch.setattr(api_gen.shutil, "which", lambda name: None)
    with pytest.raises(api_gen.GitError):
        run_mvn_compile(tmp_path)


def test_run_mvn_compile_prefers_mvn_cmd_over_extensionless(tmp_path, monkeypatch):
    """回归(WinError 193,2026-08-17 E2E):Maven bin 含无扩展名 Unix sh 脚本 "mvn",
    shutil.which("mvn") 在 Windows 先命中它而无法执行。必须优先 mvn.cmd。"""
    seen = {}

    def fake_run(args, **kw):
        seen["argv0"] = args[0]
        return subprocess.CompletedProcess(args, 0, b"", b"")

    def fake_which(name):
        return "C:/maven/bin/mvn.cmd" if name == "mvn.cmd" else "C:/maven/bin/mvn"

    monkeypatch.setattr(api_gen.shutil, "which", fake_which)
    monkeypatch.setattr(api_gen.subprocess, "run", fake_run)
    r = run_mvn_compile(tmp_path)
    assert r.success is True
    assert seen["argv0"] == "C:/maven/bin/mvn.cmd"


def test_write_files_allows_overwrite_when_ai_owned(tmp_path):
    """回归(2026-08-18 job#11 实测):AI 生成并推送过的文件再次生成时已变为 git 已跟踪,
    write_files 拒绝导致任务失败。path 在 ai_owned(AI 历史产物)集合中时应允许覆盖。"""
    import subprocess as sp

    sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "src/test/resources").mkdir(parents=True)
    prop = tmp_path / "src/test/resources/test.properties"
    prop.write_text("old", encoding="utf-8")
    sp.run(["git", "add", "."], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    sp.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)
    result = write_files(
        tmp_path,
        [{"path": "src/test/resources/test.properties", "content": "new"}],
        ai_owned={"src/test/resources/test.properties"},
    )
    assert result == [{"path": "src/test/resources/test.properties", "action": "overwritten"}]
    assert prop.read_text(encoding="utf-8") == "new"


def test_write_files_still_rejects_foreign_tracked(tmp_path):
    """ai_owned 之外的已跟踪文件(用户手写)仍拒绝覆盖——保护语义不变。"""
    import subprocess as sp

    sp.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "T.java").write_text("old", encoding="utf-8")
    sp.run(["git", "add", "."], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    sp.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    sp.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)
    with pytest.raises(Exception):
        write_files(tmp_path, [{"path": "T.java", "content": "new"}], ai_owned={"other/path.java"})


def test_ai_owned_paths_aggregates_history():
    """_ai_owned_paths 聚合本项目历史 api_generation 任务的 artifacts 路径。"""
    from app.jobs.api_gen import _ai_owned_paths

    db = SessionLocal()
    try:
        proj = Project(name="ai_owned 聚合测试")
        db.add(proj)
        db.flush()
        j1 = GenerationJob(project_id=proj.id, job_type="api_generation",
                           artifacts=[{"path": "src/test/java/A.java", "action": "created"}])
        j2 = GenerationJob(project_id=proj.id, job_type="api_generation",
                           artifacts=[{"path": "src/test/java/B.java", "action": "overwritten"},
                                      {"path": "src/test/resources/test.properties", "action": "created"}])
        case = GenerationJob(project_id=proj.id, job_type="case_generation")  # 用例任务不计入
        db.add_all([j1, j2, case])
        db.commit()
        owned = _ai_owned_paths(db, proj.id)
        assert owned == {"src/test/java/A.java", "src/test/java/B.java",
                         "src/test/resources/test.properties"}
    finally:
        db.close()


async def test_api_job_accumulates_tokens_across_rounds(monkeypatch, tmp_path):
    """A3:第 0 轮 + 修复轮两次 AI 调用,tokens 必须是两轮之和(修'末轮覆盖'缺陷)。"""
    doc_file = tmp_path / "api.md"
    doc_file.write_text("# API 文档", encoding="utf-8")
    wc = tmp_path / "wc"
    (wc / "src/test/java").mkdir(parents=True)
    calls = {"n": 0}

    async def fake_stream(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            yield ("delta", '{"files": [{"path": "src/test/java/T.java", "content": "class T{}"}]}')
            yield ("usage", (1000, 500))
        else:
            yield ("delta", '{"files": []}')
            yield ("usage", (800, 300))

    monkeypatch.setattr(ag, "stream_api_generation", fake_stream)
    monkeypatch.setattr(ag, "ensure_repo", lambda project: None)
    monkeypatch.setattr(ag, "working_copy_path", lambda project: wc)
    monkeypatch.setattr(ag, "collect_project_summary", lambda w: dict(_EMPTY_SUMMARY))
    mvn_results = [MvnResult(success=False, output="boom"), MvnResult(success=True, output="ok"), MvnResult(success=True, output="ok")]
    monkeypatch.setattr(ag, "run_mvn_compile", lambda w: mvn_results.pop(0))
    monkeypatch.setattr(ag, "estimate_cost", lambda m, i, o: 3.0)

    db = SessionLocal()
    try:
        job = _seed_api_job(db, str(doc_file))
        await ag.process_api_job(job.id)
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.status == "completed"
        assert got.input_tokens == 1800 and got.output_tokens == 800  # 1000+800 / 500+300
        assert got.output_text.count("===== 修复轮 1 =====") == 1  # A1:两轮输出都被持久化
        assert "class T{}" in got.output_text
        assert got.started_at is not None and got.finished_at is not None
    finally:
        db.close()


async def test_api_job_tokens_survive_mvn_failure(monkeypatch, tmp_path):
    """A3:mvn 三轮皆败 → failed,但每轮 tokens 都累计落库(E2E job6-9 显示 0/0 的根因)。"""
    doc_file = tmp_path / "api.md"
    doc_file.write_text("# API 文档", encoding="utf-8")
    wc = tmp_path / "wc"
    (wc / "src/test/java").mkdir(parents=True)

    async def fake_stream(*a, **kw):
        yield ("delta", '{"files": [{"path": "src/test/java/T.java", "content": "bad"}]}')
        yield ("usage", (600, 400))

    monkeypatch.setattr(ag, "stream_api_generation", fake_stream)
    monkeypatch.setattr(ag, "ensure_repo", lambda project: None)
    monkeypatch.setattr(ag, "working_copy_path", lambda project: wc)
    monkeypatch.setattr(ag, "collect_project_summary", lambda w: dict(_EMPTY_SUMMARY))
    monkeypatch.setattr(ag, "run_mvn_compile", lambda w: MvnResult(success=False, output="编译失败"))
    monkeypatch.setattr(ag, "estimate_cost", lambda m, i, o: 4.0)

    db = SessionLocal()
    try:
        job = _seed_api_job(db, str(doc_file))
        await ag.process_api_job(job.id)
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.status == "failed"
        assert got.input_tokens == 600 * 3 and got.output_tokens == 400 * 3  # 第0+2 修复轮共三次调用
        assert got.finished_at is not None
    finally:
        db.close()


async def test_api_job_persists_thinking_across_rounds(monkeypatch, tmp_path):
    """计划6:两轮 AI 的思考都落 thinking_text,带与 output_text 同款修复轮分隔符。"""
    doc_file = tmp_path / "api.md"
    doc_file.write_text("# API 文档", encoding="utf-8")
    wc = tmp_path / "wc"
    (wc / "src/test/java").mkdir(parents=True)
    calls = {"n": 0}

    async def fake_stream(*a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            yield ("thinking", "第0轮思考:设计测试类结构…")
            yield ("delta", '{"files": [{"path": "src/test/java/T.java", "content": "class T{}"}]}')
            yield ("usage", (1000, 500))
        else:
            yield ("thinking", "修复轮思考:修编译错误…")
            yield ("delta", '{"files": []}')
            yield ("usage", (800, 300))

    monkeypatch.setattr(ag, "stream_api_generation", fake_stream)
    monkeypatch.setattr(ag, "ensure_repo", lambda project: None)
    monkeypatch.setattr(ag, "working_copy_path", lambda project: wc)
    monkeypatch.setattr(ag, "collect_project_summary", lambda w: dict(_EMPTY_SUMMARY))
    mvn_results = [MvnResult(success=False, output="boom"), MvnResult(success=True, output="ok"), MvnResult(success=True, output="ok")]
    monkeypatch.setattr(ag, "run_mvn_compile", lambda w: mvn_results.pop(0))
    monkeypatch.setattr(ag, "estimate_cost", lambda m, i, o: 3.0)

    db = SessionLocal()
    try:
        job = _seed_api_job(db, str(doc_file))
        await ag.process_api_job(job.id)
        db.expire_all()
        got = db.get(GenerationJob, job.id)
        assert got.status == "completed"
        assert got.thinking_text is not None
        assert "第0轮思考" in got.thinking_text and "修复轮思考" in got.thinking_text
        assert got.thinking_text.count("===== 修复轮 1 =====") == 1
    finally:
        db.close()
