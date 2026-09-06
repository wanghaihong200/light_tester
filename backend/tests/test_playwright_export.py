# backend/tests/test_playwright_export.py
from app.ui_automation.playwright_export import render_locator, render_steps, slugify


# ---- slugify ----
def test_slugify_chinese_name():
    assert slugify(3, "登录流程") == "3_dengluliucheng"
    assert slugify(12, "Order Pay!!") == "12_order_pay"
    assert slugify(7, "!!!") == "7_script"  # 全非法字符兜底


# ---- locator:单候选 ----
def test_locator_single_candidates():
    assert render_locator([{"strategy": "test_id", "value": "submit"}]) == 'page.get_by_test_id("submit")'
    assert render_locator([{"strategy": "role", "role": "button", "name": "提交"}]) == 'page.get_by_role("button", name="提交")'
    assert render_locator([{"strategy": "role", "role": "textbox"}]) == 'page.get_by_role("textbox")'
    assert render_locator([{"strategy": "text", "value": "登录"}]) == 'page.get_by_text("登录")'
    assert render_locator([{"strategy": "css", "value": "#app .btn"}]) == 'page.locator("#app .btn")'


# ---- locator:fallbacks → or_ 链(全保真) ----
def test_locator_or_chain():
    got = render_locator([
        {"strategy": "test_id", "value": "a"},
        {"strategy": "text", "value": "b"},
    ])
    assert got == 'page.get_by_test_id("a").or_(page.get_by_text("b"))'


# ---- steps:全部选择器动作 ----
def test_render_steps_all_actions():
    steps = [
        {"id": 1, "action": "goto", "params": {"url": "https://x.example/{{host}}"}},
        {"id": 2, "action": "click", "locator": {"strategy": "test_id", "value": "btn"}},
        {"id": 3, "action": "fill", "locator": {"strategy": "placeholder", "value": "用户名"}, "params": {"text": "{{user}}"}},
        {"id": 4, "action": "press", "locator": {"strategy": "css", "value": "#s"}, "params": {"key": "Enter"}},
        {"id": 5, "action": "select_option", "locator": {"strategy": "label", "value": "城市"}, "params": {"value": "北京"}},
        {"id": 6, "action": "wait", "params": {"ms": 800}},
        {"id": 7, "action": "set_var", "params": {"name": "token", "value": "abc-{{user}}"}},
        {"id": 8, "action": "scroll", "params": {"dx": 0, "dy": 600}},
        {"id": 9, "action": "assert_visible", "locator": {"strategy": "text", "value": "欢迎"}},
        {"id": 10, "action": "assert_exists", "locator": {"strategy": "css", "value": ".list"}},
        {"id": 11, "action": "assert_text", "locator": {"strategy": "test_id", "value": "title"},
         "params": {"text": "AI 测试平台", "mode": "equals"}},
    ]
    lines, errs = render_steps(steps)
    assert errs == []
    assert lines == [
        '    page.goto(f"https://x.example/{_v(\'host\')}")',
        '    page.get_by_test_id("btn").click()',
        "    page.get_by_placeholder(\"用户名\").fill(_v('user'))",
        '    page.locator("#s").press("Enter")',
        '    page.get_by_label("城市").select_option("北京")',
        "    page.wait_for_timeout(800)",
        "    VARIABLES['token'] = f\"abc-{_v('user')}\"",
        "    page.mouse.wheel(0, 600)",
        '    expect(page.get_by_text("欢迎")).to_be_visible()',
        '    expect(page.locator(".list")).to_be_attached()',
        '    expect(page.get_by_test_id("title")).to_have_text("AI 测试平台")',
    ]


def test_render_steps_contains_mode_and_empty_params():
    lines, errs = render_steps([
        {"id": 1, "action": "assert_text", "locator": {"strategy": "text", "value": "t"},
         "params": {"text": "欢迎回来", "mode": "contains"}},
        {"id": 2, "action": "click", "locator": {"strategy": "text", "value": "x", "fallbacks": [
            {"strategy": "css", "value": "#x"}]}},
    ])
    assert errs == []
    assert lines[0] == '    expect(page.get_by_text("t")).to_contain_text("欢迎回来")'
    assert lines[1] == '    page.get_by_text("x").or_(page.locator("#x")).click()'


def test_render_steps_rejects_ai_actions():
    lines, errs = render_steps([
        {"id": 1, "action": "ai_tap", "params": {"target": "登录按钮"}},
        {"id": 2, "action": "click", "locator": {"strategy": "test_id", "value": "ok"}},
    ])
    assert len(errs) == 1
    assert "步骤1" in errs[0] and "ai_tap" in errs[0]
    assert len(lines) == 1  # 可导出步骤照常渲染
