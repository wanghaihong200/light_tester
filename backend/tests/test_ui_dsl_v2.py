# tests/test_ui_dsl_v2.py
from app.ui_automation import dsl


def _doc(version=2, target="android", steps=None):
    return {"version": version, "meta": {"target": target},
            "variables": [], "steps": steps if steps is not None else []}


def test_v1_legacy_doc_still_valid():
    doc = {"version": 1, "meta": {"start_url": "https://x"}, "variables": [],
           "steps": [{"id": "s1", "action": "click", "locator": {"strategy": "css", "value": "#a"}}]}
    assert dsl.validate_script(doc) == []


def test_v2_ai_steps_valid():
    steps = [
        {"id": "a", "action": "ai_tap", "params": {"target": "登录按钮"}},
        {"id": "b", "action": "ai_input", "params": {"target": "用户名框", "text": "u"}},
        {"id": "b2", "action": "ai_input", "params": {"text": "仅键盘输入"}},          # target 可选
        {"id": "c", "action": "ai_scroll", "params": {"direction": "down"}},
        {"id": "d", "action": "ai_wait", "params": {"assertion": "出现首页"}},
        {"id": "d2", "action": "ai_wait", "params": {"assertion": "出现首页", "timeout_ms": 15000}},
        {"id": "e", "action": "ai_assert", "params": {"assertion": "显示工作台"}},
        {"id": "f", "action": "ai_extract", "params": {"target": "订单编号", "name": "order_no"}},
        {"id": "g", "action": "run_sub", "params": {"script_id": 3}},
    ]
    assert dsl.validate_script(_doc(steps=steps)) == []


def test_v2_default_target_web():
    doc = {"version": 2, "meta": {}, "variables": [], "steps": []}
    assert dsl.validate_script(doc) == []


def test_v2_errors():
    cases = [
        (_doc(target="ios"), "target"),
        (_doc(steps=[{"id": "x", "action": "ai_tap", "params": {}}]), "缺 params.target"),
        (_doc(steps=[{"id": "x", "action": "ai_scroll", "params": {"direction": "sideways"}}]), "direction"),
        (_doc(steps=[{"id": "x", "action": "ai_wait", "params": {"assertion": "ok", "timeout_ms": -1}}]), "timeout_ms"),
        (_doc(steps=[{"id": "x", "action": "ai_wait", "params": {"assertion": "ok", "timeout_ms": True}}]), "timeout_ms"),  # bool 是 int 子类,须拒
        (_doc(steps=[{"id": "x", "action": "ai_extract", "params": {"target": "编号", "name": "9bad"}}]), "name"),
        (_doc(steps=[{"id": "x", "action": "run_sub", "params": {"script_id": "3"}}]), "script_id"),
        (_doc(steps=[{"id": "x", "action": "run_sub", "params": {}}]), "缺 params.script_id"),
    ]
    for doc, frag in cases:
        errs = dsl.validate_script(doc)
        assert errs, f"应报错: {frag}"
        assert any(frag in e for e in errs), (frag, errs)


def test_v1_rejects_ai_and_nonweb():
    e1 = dsl.validate_script(_doc(version=1, steps=[{"id": "x", "action": "ai_tap", "params": {"target": "按钮"}}]))
    assert any("version 1 不支持" in e for e in e1)
    e2 = dsl.validate_script(_doc(version=1, target="android"))
    assert any("target" in e for e in e2)
    e3 = dsl.validate_script(_doc(version=3))
    assert any("version 必须为 1 或 2" in e for e in e3)
