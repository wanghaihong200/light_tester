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
    """结构校验,返回错误列表(空列表 = 合法)。

    对畸形输入(doc/steps/params/variables 类型不对)不抛异常,
    一律记为错误条目,保证 API 层「返回 list[str]」的契约不被 500 打破。
    """
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["脚本必须是对象"]
    if doc.get("version") != 1:
        errs.append("version 必须为 1")

    steps = doc.get("steps")
    if steps is None:
        steps = []
    elif not isinstance(steps, list):
        errs.append("steps 必须是数组")
        steps = []
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            errs.append(f"步骤{i}: 必须是对象")
            continue
        action = st.get("action")
        if action not in ACTIONS:
            errs.append(f"步骤{i}: 未知 action {action!r}")
            continue
        needs = ACTIONS[action]
        if "locator" in needs and not st.get("locator"):
            errs.append(f"步骤{i}: {action} 缺 locator")
        params = st.get("params")
        if params is None:
            params = {}  # params 缺失或为 null 都视同缺参,走下方必填检查
        elif not isinstance(params, dict):
            errs.append(f"步骤{i}: params 必须是对象")
            params = None  # 类型不对:跳过该步的 params 检查
        if params is not None:
            for p in PARAM_REQUIRED.get(action, ()):
                if params.get(p) in (None, ""):
                    errs.append(f"步骤{i}: {action} 缺 params.{p}")
            if action == "wait" and not isinstance(params.get("ms"), int):
                errs.append(f"步骤{i}: wait 的 ms 必须是整数毫秒")

    variables = doc.get("variables")
    if variables is None:
        variables = []
    elif not isinstance(variables, list):
        errs.append("variables 必须是数组")
        variables = []
    for v in variables:
        if not isinstance(v, dict):
            errs.append(f"变量必须是对象: {v!r}")
            continue
        name = v.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            errs.append(f"变量名非法: {name!r}")
    return errs


def raw_locator_candidates(loc: dict) -> list[dict]:
    """primary + fallbacks 展平为候选列表,过滤掉未知 strategy,交给驱动器依次尝试。"""
    out = [loc] + list(loc.get("fallbacks") or [])
    return [c for c in out if c.get("strategy") in STRATEGIES]
