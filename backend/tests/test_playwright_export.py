# backend/tests/test_playwright_export.py
from app.ui_automation.playwright_export import _PY_HEADER, render_locator, render_steps, slugify


# ---- slugify ----
def test_slugify_chinese_name():
    assert slugify(3, "登录流程") == "3_dengluliucheng"
    assert slugify(12, "Order Pay!!") == "12_order_pay"
    assert slugify(7, "!!!") == "7_script"  # 全非法字符兜底


# ---- locator:单候选(补 .first,对齐 runner「命中也取首个」的语义) ----
def test_locator_single_candidates():
    assert render_locator([{"strategy": "test_id", "value": "submit"}]) == 'page.get_by_test_id("submit").first'
    assert render_locator([{"strategy": "role", "role": "button", "name": "提交"}]) == 'page.get_by_role("button", name="提交").first'
    assert render_locator([{"strategy": "role", "role": "textbox"}]) == 'page.get_by_role("textbox").first'
    assert render_locator([{"strategy": "text", "value": "登录"}]) == 'page.get_by_text("登录").first'
    assert render_locator([{"strategy": "css", "value": "#app .btn"}]) == 'page.locator("#app .btn").first'


# ---- locator:fallbacks → _first 逐候选尝试(语义对齐 runner._locate) ----
# 2026-09-07 冒烟缺陷:原 or_() 链是并集匹配,宽泛 fallback(css div)触发严格模式冲突
# (resolved to 266 elements),平台执行 41/41 全过而导出脚本第 3 步即挂。
def test_locator_first_helper_chain():
    got = render_locator([
        {"strategy": "test_id", "value": "a"},
        {"strategy": "text", "value": "b"},
    ])
    assert got == '_first(page.get_by_test_id("a"), page.get_by_text("b"))'


def test_first_helper_semantics_from_generated_code():
    """生成的 _first 必须复刻 runner._locate:逐候选试、命中取 .first、全空回退首个。"""
    src = _PY_HEADER.format(script_id=1, script_name="x", exported_at="2026-09-07 00:00",
                            filename="test_1_x.py", auth_note="", variables="{}")
    ns: dict = {}
    exec(compile(src, "test_1_x.py", "exec"), ns)  # 头部仅 import + 纯函数定义,可安全执行
    first = ns["_first"]

    class FakeLoc:
        def __init__(self, n, tag):
            self._n, self._tag = n, tag
        def count(self):
            return self._n
        @property
        def first(self):
            return f"{self._tag}.first"

    a_hit, b_hit = FakeLoc(1, "a"), FakeLoc(3, "b")
    assert first(a_hit, b_hit) == "a.first"          # 首候选命中即用,不看后续
    assert first(FakeLoc(0, "a"), b_hit) == "b.first"  # 首候选空,落到 fallback
    assert first(FakeLoc(0, "a"), FakeLoc(0, "b")) == "a.first"  # 全未命中回退首个(让动作超时报错)


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
        '    page.goto(f"https://x.example/{_v(\'host\')}", wait_until="domcontentloaded")',
        '    page.get_by_test_id("btn").first.click()',
        "    page.get_by_placeholder(\"用户名\").first.fill(_v('user'))",
        '    page.locator("#s").first.press("Enter")',
        '    page.get_by_label("城市").first.select_option("北京")',
        "    page.wait_for_timeout(800)",
        "    VARIABLES['token'] = f\"abc-{_v('user')}\"",
        "    page.mouse.wheel(0, 600)",
        '    expect(page.get_by_text("欢迎").first).to_be_visible()',
        '    expect(page.locator(".list").first).to_be_attached()',
        '    expect(page.get_by_test_id("title").first).to_have_text("AI 测试平台")',
    ]


def test_render_steps_contains_mode_and_empty_params():
    lines, errs = render_steps([
        {"id": 1, "action": "assert_text", "locator": {"strategy": "text", "value": "t"},
         "params": {"text": "欢迎回来", "mode": "contains"}},
        {"id": 2, "action": "click", "locator": {"strategy": "text", "value": "x", "fallbacks": [
            {"strategy": "css", "value": "#x"}]}},
    ])
    assert errs == []
    assert lines[0] == '    expect(page.get_by_text("t").first).to_contain_text("欢迎回来")'
    assert lines[1] == '    _first(page.get_by_text("x"), page.locator("#x")).click()'


def test_render_steps_rejects_ai_actions():
    lines, errs = render_steps([
        {"id": 1, "action": "ai_tap", "params": {"target": "登录按钮"}},
        {"id": 2, "action": "click", "locator": {"strategy": "test_id", "value": "ok"}},
    ])
    assert len(errs) == 1
    assert "步骤1" in errs[0] and "ai_tap" in errs[0]
    assert len(lines) == 1  # 可导出步骤照常渲染


# ---- _PY_HEADER 模板:format 后花括号保真(Task 5 将来的调用形态) ----
def test_py_header_format_keeps_placeholder_braces():
    out = _PY_HEADER.format(script_id=1, script_name="x", exported_at="2026-09-06 00:00",
                            filename="test_1_x.py", auth_note="", variables="{}")
    assert '"{{" + name + "}}"' in out  # _v 兜底表达式 format 后仍保留双花括号
    assert "{{name}}" in out  # docstring 占位符 format 后仍保留 {{name}}
    compile(out, "test_1_x.py", "exec")  # 格式化产物语法有效
