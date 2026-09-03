# app/ui_automation/events.py
"""原始采集事件 → DSL 步骤。纯函数:录制器在边界事件到来时整体 flush。"""
from app.ui_automation import dsl

_seq = 0


def _next_id() -> str:
    """会话内唯一的步骤 id;全局单调计数即可,无需跨会话重置。"""
    global _seq
    _seq += 1
    return f"st_{_seq}"


def _target_desc(t: dict) -> dict:
    """注入 JS 上报的 target 原样透传给前端/编辑器,driver 侧负责翻译成 locator。"""
    return {k: t[k] for k in ("tag", "id", "name", "classes", "type", "role",
                              "aria_label", "test_id", "placeholder", "text") if t.get(k)}


def dedupe_and_map(raw_events: list[dict]) -> list[dict]:
    """原始事件流 → 带 target 的中间步骤流。

    连续对同一元素的 input 只保留最新值;keydown 仅保留功能键
    (Enter/Escape/Tab);input 后点击同一元素视为失焦,不生成 click。
    """
    steps: list[dict] = []
    pending: dict | None = None  # 待定稿的 input:{"target":..., "value":...}

    def flush_input():
        nonlocal pending
        if pending is not None:
            steps.append({"id": _next_id(), "action": "fill",
                          "target": pending["target"], "params": {"text": pending["value"]}})
            pending = None

    for ev in raw_events:
        kind = ev["kind"]
        if kind == "input":
            if pending is not None and pending["target"] == ev.get("target"):
                pending["value"] = ev["value"]  # 同元素连续输入:只留最新值
            else:
                flush_input()
                pending = {"target": ev["target"], "value": ev["value"]}
        elif kind == "change":
            flush_input()
            steps.append({"id": _next_id(), "action": "select_option",
                          "target": ev["target"], "params": {"value": str(ev.get("value", ""))}})
        elif kind == "keydown":
            flush_input()
            if ev.get("key") in ("Enter", "Escape", "Tab"):
                steps.append({"id": _next_id(), "action": "press",
                              "target": ev["target"], "params": {"key": ev["key"]}})
        elif kind == "click":
            # 点击目标若是当前输入框(input 后点击同元素)则只保留 fill
            if not (pending is not None and pending["target"] == ev.get("target")):
                flush_input()
                steps.append({"id": _next_id(), "action": "click", "target": ev["target"]})
        elif kind == "goto":
            flush_input()
            steps.append({"id": _next_id(), "action": "goto", "params": {"url": ev["url"]}})
    flush_input()
    return steps


def target_to_locator(target: dict) -> dict:
    """按稳定性排序生成 primary + fallbacks:test_id > role > placeholder > label > text > css。"""
    cands: list[dict] = []
    if target.get("test_id"):
        cands.append({"strategy": "test_id", "value": target["test_id"]})
    if target.get("role"):
        cands.append({"strategy": "role", "role": target["role"],
                      **({"name": target.get("aria_label") or target.get("text")} if (target.get("aria_label") or target.get("text")) else {})})
    if target.get("type") in ("text", "password", "email", "search", "tel", "url") and target.get("placeholder"):
        cands.append({"strategy": "placeholder", "value": target["placeholder"]})
    if target.get("aria_label"):
        cands.append({"strategy": "label", "value": target["aria_label"]})
    text = (target.get("text") or "").strip()
    if text and target.get("tag") in ("button", "a", "span", "label", "div") and len(text) <= 40:
        cands.append({"strategy": "text", "value": text})
    if target.get("id"):
        cands.append({"strategy": "css", "value": f"#{target['id']}"})
    elif target.get("name") and target.get("tag") in ("input", "select", "textarea"):
        cands.append({"strategy": "css", "value": f"{target['tag']}[name='{target['name']}']"})
    else:
        cands.append({"strategy": "css", "value": target["tag"]})
    primary, fallbacks = cands[0], cands[1:]
    return {**primary, **({"fallbacks": fallbacks} if fallbacks else {})}


def finalize_steps(raw_steps: list[dict]) -> list[dict]:
    """把 target 翻译为 locator,产出最终 DSL 步骤(goto/wait/set_var 无 target)。"""
    out = []
    for st in raw_steps:
        s = {"id": st["id"], "action": st["action"]}
        if st.get("target"):
            s["locator"] = target_to_locator(st["target"])
        if st.get("params"):
            s["params"] = st["params"]
        out.append(s)
    return out


def step_summary(step: dict) -> str:
    """生成中文摘要,如「点击 登录」「输入 用户名=admin」「等待 1000ms」。"""
    a = step["action"]
    loc_name = (step.get("locator", {}).get("name") or step.get("locator", {}).get("value") or "") if step.get("locator") else ""
    p = step.get("params", {})
    if a == "click": return f"点击 {loc_name}"
    if a == "fill": return f"输入 {loc_name}={p.get('text', '')}"
    if a == "goto": return f"打开 {p.get('url', '')}"
    if a == "press": return f"按键 {p.get('key', '')}"
    if a == "select_option": return f"选择 {loc_name}={p.get('value', '')}"
    if a == "wait": return f"等待 {p.get('ms', 0)}ms"
    if a == "set_var": return f"设变量 {p.get('name')}={p.get('value')}"
    if a == "assert_visible": return f"断言 可见 {loc_name}"
    if a == "assert_exists": return f"断言 存在 {loc_name}"
    if a == "assert_text":
        mode = "等于" if p.get("mode") == "equals" else "包含"
        return f"断言 文本{mode} {p.get('text', '')}"
    return a
