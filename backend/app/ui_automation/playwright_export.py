# app/ui_automation/playwright_export.py
"""DSL → Python·pytest(Playwright)翻译器。纯函数零 IO,便于单测。

保真约定(2026-09-06 grilling 拍板):
- fallbacks → locator.or_() 链;variables → 文件顶部 VARIABLES 字典;{{name}} → _v('name')(未定义保留占位符,
  与 dsl.render_text 语义一致);set_var → 运行时对 VARIABLES 赋值;assert_text mode=equals/contains →
  to_have_text/to_contain_text(Playwright 文本断言自带空白归一化,与平台 normalize_ws 语义对齐);
- ai 系动作(run_sub 除外)不可确定性导出 → 记错误拒绝;run_sub 由 Task 5 的内联层处理。
"""
import re

from pypinyin import lazy_pinyin

AI_ACTIONS = ("ai_tap", "ai_input", "ai_scroll", "ai_wait", "ai_assert", "ai_extract", "run_sub")

_PY_HEADER = '''"""由轻测试平台导出的 Playwright 测试,来源脚本 #{script_id}「{script_name}」(导出于 {exported_at})。

依赖:pip install pytest pytest-playwright && python -m playwright install chromium
运行:pytest {filename} -v        # 默认 headless;加 --headed 看浏览器
{auth_note}生成区为机器翻译,变量默认值在下方 VARIABLES 中修改,请勿手改步骤代码。
"""
import pytest
from playwright.sync_api import Page, expect

VARIABLES = {variables}


def _v(name: str) -> str:
    """取变量;未定义时保留 {{name}} 占位符(与平台渲染语义一致)。"""
    return str(VARIABLES.get(name, "{{" + name + "}}"))

'''

RUN_MD_TEMPLATE = '''# Web 自动化脚本运行说明

本目录脚本由轻测试平台「Web自动化」录制导出(来源脚本:#{script_id}「{script_name}」)。

## 环境准备

```bash
pip install pytest pytest-playwright
python -m playwright install chromium
```

## 运行

```bash
pytest {filename} -v          # headless
pytest {filename} -v --headed # 有头观察
```

## 变量

脚本顶部 `VARIABLES` 字典即参数表,改值即可,无需动步骤代码。
{auth_section}
## 登录态

执行不需要平台;脚本目录内 `auth_states/` 已随仓附带 storage_state 文件。
'''

_CAND = {
    "test_id": lambda c: f'page.get_by_test_id({_dq(c["value"])})',
    "placeholder": lambda c: f'page.get_by_placeholder({_dq(c["value"])})',
    "label": lambda c: f'page.get_by_label({_dq(c["value"])})',
    "text": lambda c: f'page.get_by_text({_dq(c["value"])})',
    "css": lambda c: f'page.locator({_dq(c["value"])})',
}


def _py_str(s: str) -> str:
    return repr(s)


_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def _esc(text: str) -> str:
    """源码级转义:反斜杠/双引号/控制符(花括号除外,归 f-string 层处理)。"""
    return (text.replace("\\", "\\\\").replace('"', '\\"')
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))


def _dq(s: str) -> str:
    """双引号字符串字面量(测试契约:定位器/按键/断言文本一律双引号)。"""
    return '"' + _esc(s) + '"'


def _f_lit(text: str) -> str:
    """f-string 字面段:先做字符串转义,再把花括号翻倍。"""
    return _esc(text).replace("{", "{{").replace("}", "}}")


def slugify(script_id: int, name: str) -> str:
    """中文名转拼音式安全片段;非法字符坍缩为 _;全空兜底 script。"""
    text = "".join(lazy_pinyin(name or "")).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return f"{script_id}_{text or 'script'}"


def render_locator(candidates: list[dict]) -> str:
    """主定位器 + fallbacks → or_ 链(任一命中即操作,语义对齐 runner 的逐候选尝试)。"""
    parts: list[str] = []
    for c in candidates:
        s = c.get("strategy")
        if s == "role":
            role = _dq(c.get("role", ""))
            if c.get("name"):
                parts.append(f'page.get_by_role({role}, name={_dq(c["name"])})')
            else:
                parts.append(f"page.get_by_role({role})")
        elif s in _CAND:
            parts.append(_CAND[s](c))
    if not parts:
        raise ValueError("无可识别定位策略")
    return ".or_(".join(parts) + ")" * (len(parts) - 1)


def _interpolate(value: str) -> str:
    """字符串参数里的 {{var}} → f-string 片段。无变量时返回双引号字面量。

    拆成字面段/变量段逐一渲染:字面段经 _f_lit(转义引号反斜杠 + 花括号翻倍),变量段为 {_v('name')}。
    整串恰好是一个变量时不套 f-string,直接 _v('name');含 {{ 但无合法变量名时整体按字面量保留
    (对齐 dsl.render_text「不匹配则原样」的语义)。
    """
    if not isinstance(value, str) or "{{" not in value:
        return _dq(value) if isinstance(value, str) else _py_str(value)
    pieces: list[tuple[str, str]] = []
    pos = 0
    for m in _VAR_RE.finditer(value):
        if m.start() > pos:
            pieces.append(("lit", value[pos:m.start()]))
        pieces.append(("var", m.group(1)))
        pos = m.end()
    if pos < len(value):
        pieces.append(("lit", value[pos:]))
    if not any(kind == "var" for kind, _ in pieces):
        return _dq(value)
    if len(pieces) == 1 and pieces[0][0] == "var":
        return _v_call(pieces[0][1])
    body = "".join(
        "{" + _v_call(p[1]) + "}" if p[0] == "var" else _f_lit(p[1])
        for p in pieces
    )
    return f'f"{body}"'


def _v_call(name: str) -> str:
    return f"_v('{name}')"


def render_steps(steps: list[dict], indent: str = "    ") -> tuple[list[str], list[str]]:
    lines: list[str] = []
    errs: list[str] = []
    for idx, st in enumerate(steps, 1):
        action = st.get("action")
        try:
            if action in AI_ACTIONS and action != "run_sub":
                errs.append(f"步骤{idx}: 动作 {action} 依赖 AI 视觉定位,无法确定性导出为 Playwright 脚本")
                continue
            if action == "run_sub":
                errs.append(f"步骤{idx}: run_sub 应由内联层处理,此处不应出现")
                continue
            line = _render_single(st)
            if line is not None:
                lines.append(indent + line)
        except (KeyError, ValueError) as e:
            errs.append(f"步骤{idx}: {action} 无法导出({e})")
    return lines, errs


def _render_single(st: dict) -> str:
    action = st["action"]
    loc = st.get("locator")
    p = st.get("params") or {}
    if action == "goto":
        return f"page.goto({_interpolate(p['url'])})"
    if action in ("click", "fill", "press", "select_option"):
        base = render_locator(_candidates(loc))
        if action == "click":
            return f"{base}.click()"
        if action == "fill":
            return f"{base}.fill({_interpolate(p['text'])})"
        if action == "press":
            return f"{base}.press({_dq(p['key'])})"
        return f"{base}.select_option({_interpolate(p['value'])})"
    if action == "wait":
        return f"page.wait_for_timeout({int(p['ms'])})"
    if action == "set_var":
        return f"VARIABLES[{_py_str(p['name'])}] = {_interpolate(p['value'])}"
    if action == "scroll":
        return f"page.mouse.wheel({int(p['dx'])}, {int(p['dy'])})"
    if action == "assert_visible":
        return f"expect({render_locator(_candidates(loc))}).to_be_visible()"
    if action == "assert_exists":
        return f"expect({render_locator(_candidates(loc))}).to_be_attached()"
    if action == "assert_text":
        expect = f"expect({render_locator(_candidates(loc))})"
        if p.get("mode") == "equals":
            return f"{expect}.to_have_text({_interpolate(p['text'])})"
        return f"{expect}.to_contain_text({_interpolate(p['text'])})"
    raise ValueError(f"未知动作 {action}")


def _candidates(loc: dict | None) -> list[dict]:
    if not loc:
        raise ValueError("缺 locator")
    out = [loc] + list(loc.get("fallbacks") or [])
    return [c for c in out if c.get("strategy")]
