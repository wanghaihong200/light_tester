# app/ui_automation/playwright_export.py
"""DSL → Python·pytest(Playwright)翻译器。纯函数零 IO,便于单测。

保真约定(2026-09-06 grilling 拍板;fallbacks 语义 2026-09-07 冒烟后修正):
- fallbacks → 生成 _first() 帮助函数逐候选尝试(对齐 runner._locate:首个命中候选取 .first;
  原 or_() 链方案是并集匹配,宽泛 fallback 在严格模式下报 resolved to N elements,已证伪弃用);
  单候选也补 .first(runner 对命中候选恒取首个,容忍多元素匹配);variables → 文件顶部 VARIABLES 字典;
  {{name}} → _v('name')(未定义保留占位符,与 dsl.render_text 语义一致);set_var → 运行时对 VARIABLES 赋值;
  assert_text mode=equals/contains → to_have_text/to_contain_text(Playwright 文本断言自带空白归一化,
  与平台 normalize_ws 语义对齐);
- ai 系动作(run_sub 除外)不可确定性导出 → 记错误拒绝;run_sub 由 Task 5 的内联层处理。
"""
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

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
    """取变量;未定义时保留 {{{{name}}}} 占位符(与平台渲染语义一致)。"""
    return str(VARIABLES.get(name, "{{{{" + name + "}}}}"))


def _first(*locs):
    """逐候选尝试(与平台执行器同语义):首个有命中的定位器取其第一个元素;
    全未命中回退首个候选(让动作在等待超时报错,与执行器口径一致)。"""
    for loc in locs:
        if loc.count() > 0:
            return loc.first
    return locs[0].first

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
    """主定位器 + fallbacks → 逐候选尝试语义:多候选包进 _first(...) 调用,
    单候选补 .first(与 runner._locate「命中恒取首个」对齐)。"""
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
    if len(parts) == 1:
        return parts[0] + ".first"
    return "_first(" + ", ".join(parts) + ")"


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
        # wait_until 对齐 runner(domcontentloaded):默认 load 会被第三方统计脚本拖到超时,
        # 平台执行能过而导出脚本挂(2026-09-07 终验实测)
        return f'page.goto({_interpolate(p["url"])}, wait_until="domcontentloaded")'
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


# ---- 组装层:run_sub 内联 + 整文件生成 ----

@dataclass
class ExportBundle:
    """导出产物:仓内相对路径 → 文件内容;errors 非空时 files 必为空。"""

    files: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def _unit_fn_name(script_id: int, name: str, *, is_entry: bool) -> str:
    """entry → test_<slug>(pytest 收集约定);子脚本 → _sub_<slug>(私有,调用点与 def 同名)。"""
    return ("test_" if is_entry else "_sub_") + slugify(script_id, name)


def _render_with_calls(
    doc: dict, lookup: Callable[[int], tuple[str, dict] | None],
) -> tuple[list[str], list[str]]:
    """按原顺序渲染步骤;run_sub 位置替换为对 _sub_<slug>(page) 的调用行。"""
    lines: list[str] = []
    errs: list[str] = []
    for i, st in enumerate(doc.get("steps") or [], 1):
        if st.get("action") == "run_sub":
            ref = (st.get("params") or {}).get("script_id")
            found = lookup(ref) if isinstance(ref, int) else None
            if found is None:
                continue  # 缺失错误已在收集期记录
            lines.append(f"    {_unit_fn_name(ref, found[0], is_entry=False)}(page)")
            continue
        one, e1 = render_steps([st])
        if e1:
            errs.extend(f"步骤{i}: {m.split(':', 1)[-1].strip()}" for m in e1)
        lines.extend(one)
    return lines, errs


def _render_unit(
    doc: dict, fn_name: str, *, is_test: bool,
    lookup: Callable[[int], tuple[str, dict] | None],
) -> tuple[list[str], list[str]]:
    """一个脚本单元 → [def 行] + 体(run_sub 已内联为调用;错误透传步骤错误)。"""
    body, errs = _render_with_calls(doc, lookup)
    sig = f"def {fn_name}(page: Page):" if is_test else f"def {fn_name}(page):"
    return [sig] + (body or ["    pass"]), errs  # 空脚本兜底体必须缩进,否则生成文件 IndentationError


def _render_all_units(units: list[tuple[int, list[str]]], entry_id: int) -> str:
    """先私有 _sub_ 函数(被引用顺序),最后主 test 函数。units: [(sid, 函数行)]。"""
    subs: list[str] = []
    entry = ""
    for sid, lines in units:
        if sid == entry_id:
            entry = "\n".join(lines)
        else:
            subs.append("\n".join(lines) + "\n")
    return "\n\n".join([*subs, entry])


def _render_variables(doc: dict) -> str:
    """entry 变量表 → 多行 repr 风格字典源码(每行一个 "name": "default");空表 → "{}"。"""
    rows = [
        f'    {_dq(str(v.get("name") or ""))}: {_dq(str(v.get("default") or ""))}'
        for v in (doc.get("variables") or [])
    ]
    if not rows:
        return "{}"
    return "{\n" + ",\n".join(rows) + ",\n}"


def _has_auth(doc: dict) -> bool:
    """entry 是否挂了登录态(auth_state_id;登录态导出小节由 Task 6 接入)。"""
    return bool((doc.get("meta") or {}).get("auth_state_id"))


def collect_export_bundle(
    script_id: int,
    script_name: str,
    entry_doc: dict,
    lookup: Callable[[int], tuple[str, dict] | None],
) -> ExportBundle:
    """组装导出产物:内联 run_sub 依赖图为单文件 pytest 脚本 + RUN.md。

    任一错误(引用缺失/循环引用/步骤不可导出,含嵌套子脚本的步骤错误)→ errors 非空且 files 为空。
    """
    bundle = ExportBundle()
    errors: list[str] = []
    # 灰黑双色迭代 DFS 收集 run_sub 依赖图:灰=展开中(再遇即回边→环),黑=完成(菱形依赖只收一次)。
    state: dict[int, int] = {}  # 1=灰 2=黑
    units: list[tuple[int, str, dict]] = []  # 后序:被引用脚本先出现
    stack: list[tuple[int, str, dict, bool]] = [(script_id, script_name, entry_doc, False)]
    while stack:
        sid, name, doc, done = stack.pop()
        if done:
            state[sid] = 2
            units.append((sid, name, doc))
            continue
        mark = state.get(sid)
        if mark == 1:  # 回边:展开中的祖先又被引用 → 循环
            errors.append(f"脚本「{name}」(#{sid}) 循环引用,无法导出")
            continue
        if mark == 2:  # 已收集过(菱形依赖的第二条入边),不重复入列
            continue
        state[sid] = 1
        stack.append((sid, name, doc, True))
        for i, st in reversed(list(enumerate(doc.get("steps") or [], 1))):
            if st.get("action") != "run_sub":
                continue
            ref = (st.get("params") or {}).get("script_id")
            found = lookup(ref) if isinstance(ref, int) else None
            if found is None:
                errors.append(f"步骤{i}: run_sub 引用的脚本 #{ref} 不存在或已删除")
                continue
            stack.append((ref, found[0], found[1], False))
    if not errors:
        rendered: list[tuple[int, list[str]]] = []
        for sid, name, doc in units:
            lines, errs = _render_unit(
                doc, _unit_fn_name(sid, name, is_entry=sid == script_id),
                is_test=sid == script_id, lookup=lookup,
            )
            rendered.append((sid, lines))
            errors.extend(errs)
    if errors:
        bundle.errors = errors
        return bundle  # 有错误不产文件
    filename = f"{_unit_fn_name(script_id, script_name, is_entry=True)}.py"
    code = _PY_HEADER.format(
        script_id=script_id,
        script_name=script_name,
        exported_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        filename=filename,
        auth_note="",
        variables=_render_variables(entry_doc),
    ) + "\n" + _render_all_units(rendered, script_id) + "\n"
    bundle.files[filename] = code
    bundle.files["RUN.md"] = RUN_MD_TEMPLATE.format(
        script_id=script_id, script_name=script_name, filename=filename,
        auth_section="",  # 登录态小节 Task 6 接入
    )
    return bundle
