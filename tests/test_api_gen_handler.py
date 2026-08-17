# tests/test_api_gen_handler.py
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.jobs import api_gen
from app.jobs.api_gen import ApiFilesPayload, parse_api_files, write_files, run_mvn_compile, collect_project_summary


def test_parse_api_files_strips_fence_and_validates():
    text = '```json\n{"files":[{"path":"src/test/java/T.java","content":"class T{}"}]}\n```'
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
