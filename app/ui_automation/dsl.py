# app/ui_automation/dsl.py
"""DSL 纯函数层:校验/变量渲染/定位候选。不依赖 Playwright,可独立单测。"""
import re

ACTIONS = {
    "goto": (), "click": ("locator",), "fill": ("locator",), "press": ("locator",),
    "select_option": ("locator",), "wait": (), "set_var": (),
    "assert_visible": ("locator",), "assert_exists": ("locator",), "assert_text": ("locator",),
}
PARAM_REQUIRED = {"goto": ("url",), "fill": ("text",), "press": ("key",),
                  "select_option": ("value",), "wait": ("ms",), "set_var": ("name", "value"),
                  "assert_text": ("text",)}
STRATEGIES = {"test_id", "role", "placeholder", "label", "text", "css"}
_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def render_text(value: str, variables: dict) -> str:
    """把 `{{name}}` 替换为变量值;未定义的变量原样保留。非字符串输入原样返回。"""

    def _sub(m: re.Match) -> str:
        return str(variables.get(m.group(1), m.group(0)))

    return _VAR.sub(_sub, value) if isinstance(value, str) else value


def validate_script(doc: dict) -> list[str]:
    """结构校验,返回错误列表(空列表 = 合法)。"""
    errs: list[str] = []
    if doc.get("version") != 1:
        errs.append("version 必须为 1")
    for i, st in enumerate(doc.get("steps") or [], 1):
        action = st.get("action")
        if action not in ACTIONS:
            errs.append(f"步骤{i}: 未知 action {action!r}")
            continue
        needs = ACTIONS[action]
        if "locator" in needs and not st.get("locator"):
            errs.append(f"步骤{i}: {action} 缺 locator")
        for p in PARAM_REQUIRED.get(action, ()):
            if st.get("params", {}).get(p) in (None, ""):
                errs.append(f"步骤{i}: {action} 缺 params.{p}")
        if action == "wait" and not isinstance(st.get("params", {}).get("ms"), int):
            errs.append(f"步骤{i}: wait 的 ms 必须是整数毫秒")
    for v in doc.get("variables") or []:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", v.get("name", "")):
            errs.append(f"变量名非法: {v.get('name')!r}")
    return errs


def raw_locator_candidates(loc: dict) -> list[dict]:
    """primary + fallbacks 展平为候选列表,过滤掉未知 strategy,交给驱动器依次尝试。"""
    out = [loc] + list(loc.get("fallbacks") or [])
    return [c for c in out if c.get("strategy") in STRATEGIES]
