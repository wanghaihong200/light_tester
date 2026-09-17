# backend/tests/test_cicd_ui_selection.py
"""计划 17 Task 5:ui selection 语义切换——{file_path, function} + nodeid + 注册表 stale 校验。"""
import pytest
from fastapi import HTTPException

from app.cicd import executor
from app.models import ExecutionPlan, InterfaceCase, Project
from app.routers.cicd import _enrich_selection


@pytest.fixture
def ui_plan(db_session):
    db_session.add(Project(id=5, name="sel"))
    db_session.commit()
    db_session.add_all([
        InterfaceCase(project_id=5, branch="main", case_type="web",
                      class_name="tests/test_smoke.py", method="test_a", status="active",
                      framework="pytest"),
        InterfaceCase(project_id=5, branch="main", case_type="web",
                      class_name="tests/test_smoke.py", method="test_gone", status="stale",
                      framework="pytest"),
    ])
    db_session.commit()
    return ExecutionPlan(project_id=5, name="p", kind="ui", branch="main", selection=[])


def _write_ws(tmp_path):
    f = tmp_path / "tests" / "test_smoke.py"
    f.parent.mkdir(exist_ok=True)
    f.write_text("def test_a():\n    pass\n", encoding="utf-8")
    return tmp_path


def test_ui_selection_nodeid_and_stale(db_session, ui_plan, tmp_path):
    ws = _write_ws(tmp_path)
    ui_plan.selection = [
        {"file_path": "tests/test_smoke.py", "function": "test_a"},      # active+文件在 → 可执行
        {"file_path": "tests/test_smoke.py", "function": "test_gone"},   # stale → skipped/stale
        {"file_path": "tests/test_smoke.py", "function": "test_missing_row"},  # 无注册行 → stale
    ]
    snap, arg = executor._resolve_selection(db_session, ui_plan, ws)
    assert [s["skip_reason"] for s in snap[1:]] == ["stale", "stale"]
    assert snap[0]["skipped"] is False
    assert arg == "tests/test_smoke.py::test_a"


def test_ui_selection_active_but_file_missing(db_session, ui_plan, tmp_path):
    ui_plan.selection = [{"file_path": "tests/test_smoke.py", "function": "test_a"}]
    snap, arg = executor._resolve_selection(db_session, ui_plan, tmp_path)  # 空工作区
    assert snap[0]["skipped"] is True and snap[0]["skip_reason"] == "file_missing"
    assert arg == ""


def test_ui_selection_legacy_form_skipped_as_stale(db_session, ui_plan, tmp_path):
    """存量计划不编辑直接触发:旧形态无 file_path/function → 全 stale → 空 SELECTION → 触发 400。"""
    ws = _write_ws(tmp_path)
    ui_plan.selection = [{"script_id": 7, "name": "旧脚本", "file": "test_7_old.py"}]
    snap, arg = executor._resolve_selection(db_session, ui_plan, ws)
    assert snap[0]["skip_reason"] == "stale" and arg == ""


def test_enrich_ui_selection_new_and_legacy(db_session):
    ok = _enrich_selection("ui", [{"file_path": "tests/test_a.py", "function": "test_x"}])
    assert ok == [{"file_path": "tests/test_a.py", "function": "test_x"}]
    with pytest.raises(HTTPException) as ei:
        _enrich_selection("ui", [{"script_id": 7, "name": "旧脚本"}])
    assert "重新扫描勾选" in ei.value.detail
    api_ok = _enrich_selection("api", [{"class_name": "com.x.A", "method": "m"}])
    assert api_ok == [{"ref": "com.x.A#m", "class_name": "com.x.A", "method": "m"}]  # api 不变
