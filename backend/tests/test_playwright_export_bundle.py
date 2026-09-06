# backend/tests/test_playwright_export_bundle.py
import ast

from app.ui_automation.playwright_export import collect_export_bundle

ENTRY = {
    "version": 2, "meta": {"target": "web"},
    "variables": [{"name": "user", "default": "alice"}],
    "steps": [
        {"id": 1, "action": "goto", "params": {"url": "https://x.example/login"}},
        {"id": 2, "action": "run_sub", "params": {"script_id": 2}},
        {"id": 3, "action": "assert_visible", "locator": {"strategy": "text", "value": "首页"}},
    ],
}
SUB = {
    "version": 2, "meta": {"target": "web"}, "variables": [],
    "steps": [
        {"id": 1, "action": "fill", "locator": {"strategy": "placeholder", "value": "用户名"},
         "params": {"text": "{{user}}"}},
        {"id": 2, "action": "click", "locator": {"strategy": "test_id", "value": "submit"}},
    ],
}


def _lookup(sid: int):
    docs = {1: ("登录流程", ENTRY), 2: ("填充表单", SUB)}
    return docs.get(sid)


def test_bundle_inlines_run_sub():
    b = collect_export_bundle(1, "登录流程", ENTRY, _lookup)
    assert b.errors == []
    assert set(b.files) == {"test_1_dengluliucheng.py", "RUN.md"}
    code = b.files["test_1_dengluliucheng.py"]
    # 变量表进 header
    assert "VARIABLES" in code and '"user": "alice"' in code.replace("'", '"') or '"user"' in code
    # run_sub 内联为函数调用,被引脚本成为私有函数
    assert "def _sub_2_tianchongbiaodan(page):" in code
    assert "_sub_2_tianchongbiaodan(page)" in code
    # 主流程为 test 函数
    assert "def test_1_dengluliucheng(page: Page):" in code
    # RUN.md 含来源与运行说明
    assert "登录流程" in b.files["RUN.md"] and "pytest-playwright" in b.files["RUN.md"]


def test_bundle_missing_sub_script():
    b = collect_export_bundle(1, "登录流程", ENTRY, lambda sid: None)
    assert any("步骤2" in e and "run_sub" in e for e in b.errors)


def test_bundle_cycle_guard():
    cyc = {
        "version": 2, "meta": {"target": "web"}, "variables": [],
        "steps": [{"id": 1, "action": "run_sub", "params": {"script_id": 9}}],
    }
    b = collect_export_bundle(9, "环", cyc, lambda sid: ("环", cyc))
    assert any("循环引用" in e for e in b.errors)


def test_bundle_ai_step_rejected_with_all_errors():
    doc = {
        "version": 2, "meta": {"target": "web"}, "variables": [],
        "steps": [
            {"id": 1, "action": "ai_tap", "params": {"target": "登录按钮"}},
            {"id": 2, "action": "ai_assert", "params": {"assertion": "出现弹窗"}},
        ],
    }
    b = collect_export_bundle(5, "AI脚本", doc, lambda sid: None)
    assert len(b.errors) == 2
    assert b.files == {}  # 有错误就不产文件


def test_bundle_v1_accepted():
    doc = {"version": 1, "steps": [{"id": 1, "action": "goto", "params": {"url": "https://a"}}]}
    b = collect_export_bundle(5, "v1脚本", doc, lambda sid: None)
    assert b.errors == []
    assert list(b.files) == ["test_5_v1jiaoben.py", "RUN.md"]


def test_bundle_code_is_valid_python():
    b = collect_export_bundle(1, "登录流程", ENTRY, _lookup)
    ast.parse(b.files["test_1_dengluliucheng.py"])
