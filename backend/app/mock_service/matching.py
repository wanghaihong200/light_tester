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


def rule_matches(rule, method: str, path: str, query, headers, body: bytes) -> dict[str, str] | None:
    if not rule.enabled:
        return None
    if rule.method.upper() != method.upper():
        return None
    captured = match_path(rule.path_template, path)
    if captured is None:
        return None
    for cond in rule.conditions or []:
        if not _cond_ok(cond, query, headers, body):
            return None
    return captured


def pick_rule(rules, method: str, path: str, query, headers, body: bytes):
    for rule in rules:
        captured = rule_matches(rule, method, path, query, headers, body)
        if captured is not None:
            return rule, captured
    return None, {}
