# tests/test_ui_compose.py
from app.ui_automation import compose


def _sub(steps):
    return {"version": 2, "meta": {}, "steps": steps}


def test_expand_inlines_and_keeps_order():
    steps = [
        {"id": "1", "action": "ai_tap", "params": {"target": "我的"}},
        {"id": "2", "action": "run_sub", "params": {"script_id": 7}},
        {"id": "3", "action": "ai_assert", "params": {"assertion": "已登录"}},
    ]
    out, errs = compose.expand_steps(steps, lambda sid: _sub([
        {"id": "s1", "action": "ai_tap", "params": {"target": "登录入口"}},
        {"id": "s2", "action": "ai_input", "params": {"text": "{{pwd}}"}},
    ]))
    assert errs == []
    assert [st["id"] for st in out] == ["1", "s1", "s2", "3"]


def test_expand_cycle_and_missing():
    cyc = [{"id": "1", "action": "run_sub", "params": {"script_id": 1}}]
    _, errs = compose.expand_steps(cyc, lambda sid: _sub(cyc))
    assert any("环" in e for e in errs)
    _, errs2 = compose.expand_steps([{"id": "1", "action": "run_sub", "params": {"script_id": 99}}],
                                    lambda sid: None)
    assert any("找不到" in e for e in errs2)


def test_expand_depth_chain():
    # 深度链:7 > max_depth 5(链上 script_id 递增且各不相同;自引用会先被环检测拦截,测不出深度)
    deep = {"steps": [{"id": "1", "action": "run_sub", "params": {"script_id": 1}}]}
    _, errs3 = compose.expand_steps(
        deep["steps"],
        lambda sid: {"steps": [{"id": f"d{sid}", "action": "run_sub", "params": {"script_id": sid + 1}}]},
        max_depth=5)
    assert any("深度" in e for e in errs3)
