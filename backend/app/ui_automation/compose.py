# app/ui_automation/compose.py
"""脚本组合层:run_sub 片段展开。
展开只发生在创建执行时(路由层),不改脚本原文;展开后才会做执行路径分流。"""


def expand_steps(steps: list, resolve_sub, *, max_depth: int = 5) -> tuple[list[dict], list[str]]:
    """深度优先展开 run_sub。resolve_sub(script_id) 由调用方注入(查库取被引脚本文档,查不到返回 None)。
    返回 (展开后步骤, 错误列表)。环引用与超深度都报错不抛异常。"""
    errs: list[str] = []
    out: list[dict] = []

    def walk(items, stack: set[int]) -> None:
        for st in items:
            if not isinstance(st, dict) or st.get("action") != "run_sub":
                out.append(st)
                continue
            sid = (st.get("params") or {}).get("script_id")
            if sid in stack:
                errs.append(f"run_sub 环引用: script_id={sid} 已在展开链中")
                continue
            if len(stack) >= max_depth:
                errs.append(f"run_sub 展开深度超过 {max_depth}")
                continue
            sub = resolve_sub(sid)
            if sub is None:
                errs.append(f"run_sub 找不到脚本: script_id={sid}")
                continue
            walk(sub.get("steps") or [], stack | {sid})

    walk(steps or [], set())
    return out, errs
