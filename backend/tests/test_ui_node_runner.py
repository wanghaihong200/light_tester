# tests/test_ui_node_runner.py
import json
import sys
import time
from pathlib import Path

import pytest

from app.ui_automation import node_runner

DOC = {"version": 2, "meta": {"target": "web", "start_url": "https://x"},
       "variables": [{"name": "username", "default": "admin"}],
       "steps": [{"id": "s1", "action": "ai_tap", "params": {"target": "按钮"}}]}


def _stub(tmp_path: Path, lines: list[dict], *, sleep_after: float = 0.0) -> Path:
    stub = tmp_path / "stub_runner.py"
    body = ["import json,sys,time",
            f"time.sleep({sleep_after}) if False else None",
            # argv[1]=lines.json 路径(execute_ai_run 会在 node_cmd 后追加 job.json 为 argv[2]);
            # sys.argv 不含解释器,argv[0] 是 stub 自身,故不是 argv[2]
            "for ln in json.loads(open(sys.argv[1], encoding='utf-8').read()):",
            "    print(json.dumps(ln), flush=True)",
            f"time.sleep({sleep_after})"]
    stub.write_text("\n".join(body), encoding="utf-8")
    (tmp_path / "lines.json").write_text(json.dumps(lines), encoding="utf-8")
    return stub


def _run(tmp_path, monkeypatch, stub, lines, **kw):
    monkeypatch.setattr("app.config.settings.ui_runner_dir", tmp_path)
    events: list[dict] = []
    ret = node_runner.execute_ai_run(
        1, DOC, driver_target="web", mode="headless", data_dir=tmp_path,
        variables={"username": "root"}, storage_state=None,
        notify=events.append,
        node_cmd=[sys.executable, str(stub), str(tmp_path / "lines.json")],
        env_extra={"K": "V"}, **kw)
    return ret, events


def test_happy_path_forwards_events_and_returns_usage(tmp_path, monkeypatch):
    stub = _stub(tmp_path, [
        {"type": "frame", "data": "xx", "step_index": 0},
        {"type": "step_end", "index": 0, "step_id": "s1", "action": "ai_tap",
         "status": "passed", "error": None, "screenshot": "step_0_passed.jpg", "elapsed_ms": 5},
        {"type": "done", "status": "completed", "summary": {"total": 1, "passed": 1, "failed": 0,
         "duration_ms": 9}, "usage": {"input_tokens": 10, "output_tokens": 2}, "report_path": "r.html"},
    ])
    ret, events = _run(tmp_path, monkeypatch, stub, json.loads((tmp_path / "lines.json").read_text()))
    assert [e["type"] for e in events] == ["frame", "step_end", "done"]
    assert ret["usage"]["input_tokens"] == 10 and ret["report_path"] == "r.html"
    job = json.loads((tmp_path / "runs" / "1" / "_job" / "job.json").read_text(encoding="utf-8"))
    assert job["target"] == "web" and job["steps"][0]["params"]["target"] == "按钮"
    assert job["variables"] == {"username": "root"} and job["storage_state"] == ""


def test_crash_without_done_raises(tmp_path, monkeypatch):
    stub = _stub(tmp_path, [{"type": "step_start", "index": 0}])
    (tmp_path / "stub_runner.py").write_text(
        "import sys\nprint('{\"type\": \"step_start\", \"index\": 0}', flush=True)\n"
        "import os; os._exit(3)\n", encoding="utf-8")
    monkeypatch.setattr("app.config.settings.ui_runner_dir", tmp_path)
    with pytest.raises(RuntimeError, match="Node runner"):
        node_runner.execute_ai_run(1, DOC, driver_target="web", mode="headless",
                                   data_dir=tmp_path, notify=lambda e: None,
                                   node_cmd=[sys.executable, str(tmp_path / "stub_runner.py")])


def test_force_finish_kills_and_returns_quietly(tmp_path, monkeypatch):
    lines = [{"type": "frame", "data": "x", "step_index": 0}]
    stub = tmp_path / "stub_runner.py"
    stub.write_text(
        "import json,sys,time\n"
        "print(json.dumps(" + json.dumps(lines[0]) + "), flush=True)\n"
        "time.sleep(30)\n", encoding="utf-8")
    monkeypatch.setattr("app.config.settings.ui_runner_dir", tmp_path)
    t0 = time.monotonic()
    ret = node_runner.execute_ai_run(
        1, DOC, driver_target="web", mode="headless", data_dir=tmp_path,
        notify=lambda e: None, node_cmd=[sys.executable, str(stub)],
        poll_force=lambda rid: True)
    assert ret == {"force_finished": True}
    assert time.monotonic() - t0 < 10
