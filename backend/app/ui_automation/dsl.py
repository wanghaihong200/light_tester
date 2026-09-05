# app/ui_automation/dsl.py
"""DSL 纯函数层:校验/变量渲染/定位候选。不依赖 Playwright,可独立单测。"""
import re

# v2 多端:合法端 / ai_scroll 方向枚举 / 变量名规则 / ai 系动作清单(须先于 ACTIONS 定义)
TARGETS = {"web", "android", "harmony"}
_SCROLL_DIRECTIONS = {"up", "down", "left", "right"}
_VARNAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
AI_ACTIONS = ("ai_tap", "ai_input", "ai_scroll", "ai_wait", "ai_assert", "ai_extract", "run_sub")

ACTIONS = {
    "goto": (), "click": ("locator",), "fill": ("locator",), "press": ("locator",),
    "select_option": ("locator",), "wait": (), "set_var": (), "scroll": (),
    "assert_visible": ("locator",), "assert_exists": ("locator",), "assert_text": ("locator",),
    # version 2 扩展:ai 系六动作 + run_sub(均为无 locator 的参数驱动动作)
    **{a: () for a in AI_ACTIONS},
}
PARAM_REQUIRED = {"goto": ("url",), "fill": ("text",), "press": ("key",),
                  "select_option": ("value",), "wait": ("ms",), "set_var": ("name", "value"),
                  "scroll": ("dx", "dy"), "assert_text": ("text",),
                  "ai_tap": ("target",), "ai_input": ("text",), "ai_scroll": ("direction",),
                  "ai_wait": ("assertion",), "ai_assert": ("assertion",),
                  "ai_extract": ("target", "name"), "run_sub": ("script_id",)}
STRATEGIES = {"test_id", "role", "placeholder", "label", "text", "css"}
_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def render_text(value: str, variables: dict) -> str:
    """把 `{{name}}` 替换为变量值;未定义的变量原样保留。非字符串输入原样返回。"""

    def _sub(m: re.Match) -> str:
        return str(variables.get(m.group(1), m.group(0)))

    return _VAR.sub(_sub, value) if isinstance(value, str) else value


def normalize_ws(value: str) -> str:
    """文本比较前的空白归一化(对齐 Playwright text= 语义):连续空白(含换行/制表)坍缩为单个空格并去首尾。"""
    return " ".join(value.split()) if isinstance(value, str) else value


def text_matches(actual: str, want: str, mode: str = "contains") -> bool:
    """assert_text 的比较语义:双方先空白归一化,再按 mode 判等/包含。未知 mode 按 contains 兜底。"""
    a, w = normalize_ws(actual), normalize_ws(want)
    return (a == w) if mode == "equals" else (w in a)


def validate_script(doc: dict) -> list[str]:
    """结构校验,返回错误列表(空列表 = 合法)。

    对畸形输入(doc/steps/params/variables 类型不对)不抛异常,
    一律记为错误条目,保证 API 层「返回 list[str]」的契约不被 500 打破。
    """
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["脚本必须是对象"]
    if doc.get("version") not in (1, 2):
        errs.append("version 必须为 1 或 2")

    # meta.target:v2 多端规则(缺省视同 web;v1 只允许 web)
    meta = doc.get("meta") if isinstance(doc.get("meta"), dict) else {}
    target = meta.get("target")
    if target is not None and target not in TARGETS:
        errs.append(f"meta.target 非法: {target!r}(必须是 web/android/harmony)")
    if doc.get("version") == 1 and target not in (None, "web"):
        errs.append("version 1 脚本的 meta.target 必须是 web")

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
        # ── v2 扩展校验(params 非 dict 时沿用「视同缺参/跳过」既有逻辑)──
        if doc.get("version") == 1 and action in AI_ACTIONS:
            errs.append(f"步骤{i}: version 1 不支持 {action},请改用 version 2")
            continue
        if action == "run_sub" and not (isinstance(params, dict)
                and isinstance(params.get("script_id"), int) and not isinstance(params.get("script_id"), bool)
                and params.get("script_id") > 0):
            errs.append(f"步骤{i}: run_sub 缺合法 params.script_id(正整数)")
        if action == "ai_scroll" and isinstance(params, dict) and params.get("direction") not in _SCROLL_DIRECTIONS:
            errs.append(f"步骤{i}: ai_scroll 的 direction 必须是 up/down/left/right")
        if action == "ai_wait" and isinstance(params, dict) and "timeout_ms" in params \
                and (not isinstance(params["timeout_ms"], int) or isinstance(params["timeout_ms"], bool)
                     or params["timeout_ms"] <= 0):
            # 与 run_sub.script_id 同型:bool 是 int 子类,须显式排除(true 不是正整数毫秒)
            errs.append(f"步骤{i}: ai_wait 的 timeout_ms 必须是正整数毫秒")
        if action == "ai_extract" and isinstance(params, dict) \
                and not _VARNAME_RE.fullmatch(str(params.get("name") or "")):
            errs.append(f"步骤{i}: ai_extract 的 name 必须是合法变量名")
        if params is not None:
            for p in PARAM_REQUIRED.get(action, ()):
                if params.get(p) in (None, ""):
                    errs.append(f"步骤{i}: {action} 缺 params.{p}")
            if action == "wait" and not isinstance(params.get("ms"), int):
                errs.append(f"步骤{i}: wait 的 ms 必须是整数毫秒")
            if action == "scroll":
                for axis in ("dx", "dy"):
                    if not isinstance(params.get(axis), int):
                        errs.append(f"步骤{i}: scroll 的 {axis} 必须是整数像素")

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
