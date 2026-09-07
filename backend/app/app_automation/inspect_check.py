"""前置/后置检查点评估(纯函数)。ADR-0008:平台插不进用例中间,只有执行前后的整树观察(inspect)。
检查定义两种:
  {"type": "element_exists", "text"?: str, "resource_id"?: str, "description"?: str}
      —— 至少一个条件,多条件 AND;resource_id 支持全名(com.app:id/btn)或短名(btn)后缀匹配
  {"type": "text_contains", "value": str} —— 任一节点 text 包含即命中"""

CHECK_TYPES = ("element_exists", "text_contains")


def validate_checks(checks) -> list[str]:
    if not isinstance(checks, list):
        return ["检查点必须是数组"]
    errs: list[str] = []
    for i, c in enumerate(checks, 1):
        if not isinstance(c, dict) or c.get("type") not in CHECK_TYPES:
            errs.append(f"检查点{i}: type 必须是 {'/'.join(CHECK_TYPES)}")
            continue
        if c["type"] == "element_exists":
            if not any(c.get(k) for k in ("text", "resource_id", "description")):
                errs.append(f"检查点{i}: element_exists 至少要给 text/resource_id/description 之一")
        elif not str(c.get("value") or "").strip():
            errs.append(f"检查点{i}: text_contains 需要 value")
    return errs


def _iter_nodes(node: dict):
    yield node
    for child in node.get("children") or []:
        if isinstance(child, dict):
            yield from _iter_nodes(child)


def _rid_matches(node_rid, want: str) -> bool:
    if not node_rid:
        return False
    return node_rid == want or node_rid.endswith(f"/{want}")


def evaluate_checks(page_tree: dict, checks: list[dict]) -> list[dict]:
    """page_tree = inspect 响应里的 "page" 节点;返回逐条 {"type","passed","detail"}。"""
    nodes = list(_iter_nodes(page_tree or {}))
    results: list[dict] = []
    for c in checks or []:
        if c.get("type") == "text_contains":
            value = str(c.get("value") or "")
            hit = next((n for n in nodes if value in (n.get("text") or "")), None)
            results.append({"type": "text_contains", "passed": hit is not None,
                            "detail": f"文本「{value}」" + (f" 命中: {hit.get('text')}" if hit else " 未出现")})
            continue
        text, rid, desc = c.get("text"), c.get("resource_id"), c.get("description")
        hit = None
        for n in nodes:
            if text is not None and n.get("text") != text:
                continue
            if rid and not _rid_matches(n.get("resourceId"), rid):
                continue
            if desc is not None and n.get("description") != desc:
                continue
            hit = n
            break
        cond = " 且 ".join(filter(None, [
            f"text={text!r}" if text is not None else "",
            f"resource_id={rid!r}" if rid else "",
            f"description={desc!r}" if desc is not None else ""]))
        results.append({"type": "element_exists", "passed": hit is not None,
                        "detail": (f"找到节点 bound={hit.get('nodeBound')}" if hit else f"未找到({cond})")})
    return results
