"""Mock 规则匹配引擎(纯函数,零 IO——子进程每请求调用)。"""
import json
import re

from jsonpath_ng.ext import parse as _jsonpath_parse

HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

_SEGMENT_VAR = re.compile(r"^\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def validate_path_template(pattern: str) -> list[str]:
    errs: list[str] = []
    if not pattern.startswith("/"):
        errs.append("路径须以 / 开头")
    for seg in pattern.strip("/").split("/"):
        if seg.count("{") != seg.count("}"):
            errs.append(f"路径段 {seg!r} 花括号不配对")
        elif "{" in seg and not _SEGMENT_VAR.match(seg):
            errs.append(f"路径段 {seg!r} 变量须形如 {{name}}")
    return errs


def match_path(pattern: str, actual: str) -> dict[str, str] | None:
    p_segs = pattern.strip("/").split("/")
    a_segs = actual.strip("/").split("/")
    if len(p_segs) != len(a_segs):
        return None
    captured: dict[str, str] = {}
    for p, a in zip(p_segs, a_segs):
        m = _SEGMENT_VAR.match(p)
        if m:
            captured[m[1]] = a
        elif p != a:
            return None
    return captured


def _typed(expected: str) -> tuple[bool, object]:
    """期望值按 JSON 字面解析(number/bool/null/带引号串);解析失败按原文串。"""
    try:
        return True, json.loads(expected)
    except (json.JSONDecodeError, ValueError):
        return False, expected


def _node_str(node) -> str:
    """JSONPath 命中节点统一转串(bool/null 用 JSON 字面,容器 dumps)。"""
    if isinstance(node, bool):
        return "true" if node else "false"
    if node is None:
        return "null"
    if isinstance(node, str):
        return node
    return json.dumps(node, ensure_ascii=False)


def _value_matches(match_mode: str, expected: str, node) -> bool:
    if match_mode == "regex":
        try:
            return re.search(expected, _node_str(node)) is not None
        except re.error:
            return False  # 非法正则=条件不成立,不抛 500
    ok, typed = _typed(expected)
    if ok and not isinstance(typed, str):
        return type(node) is type(typed) and node == typed or _node_str(node) == expected
    return _node_str(node) == expected


def _cond_ok(cond: dict, query, headers, body: bytes) -> bool:
    scope, key, mode, value = cond.get("scope"), cond.get("key", ""), cond.get("match", "eq"), cond.get("value", "")
    if scope == "query":
        return any(_value_matches(mode, value, v) for v in query.get(key, []))
    if scope == "header":
        return any(_value_matches(mode, value, v) for v in headers.get(key.lower(), []))
    # body:JSONPath 定位;请求体非合法 JSON/表达式非法/无节点 → 条件不成立
    try:
        doc = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return False
    try:
        expr = _jsonpath_parse(key)
    except Exception:
        return False
    found = expr.find(doc)
    return any(_value_matches(mode, value, f.value) for f in found)


def route_matches(group, method: str, path: str) -> bool:
    """组的路由(method+路径模板)是否匹配实际请求;方法忽略大小写。"""
    return group.method.upper() == method.upper() and match_path(group.path_template, path) is not None


def pick_rule(groups, method: str, path: str, query, headers, body: bytes):
    """层级匹配(ADR-0011):按组序遍历 → 组级停用整组跳过 → 组内按序,首条命中即生效。
    groups 形如 [(group, [rules...]), ...],组间/组内均已有序且不含软删行。"""
    for group, rules in groups:
        if not group.enabled:
            continue
        captured = match_path(group.path_template, path)
        if captured is None or group.method.upper() != method.upper():
            continue
        for rule in rules:
            if not rule.enabled:
                continue
            if all(_cond_ok(c, query, headers, body) for c in rule.conditions or []):
                return rule, group, captured
    return None, None, {}
