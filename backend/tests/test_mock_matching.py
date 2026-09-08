"""匹配引擎:路径模板/条件 AND/JSONPath/正则/首条命中。"""
from types import SimpleNamespace as NS

from app.mock_service.matching import (
    match_path, pick_rule, rule_matches, validate_path_template,
)


def _rule(method="GET", path="/users/{id}", conditions=None, enabled=True):
    return NS(method=method, path_template=path, conditions=conditions or [], enabled=enabled)


def test_validate_path_template_errors():
    assert validate_path_template("/a/b") == []
    assert validate_path_template("/a/{id}") == []
    assert validate_path_template("a/b")          # 未以 / 开头
    assert validate_path_template("/a/{id")       # 花括号不配对
    assert validate_path_template("/a/{a{b}}")    # 段内非单变量
    assert validate_path_template("/a/x{y}")      # 混合字面+花括号不合法


def test_match_path_exact_and_template():
    assert match_path("/users/42/orders", "/users/42/orders") == {}
    assert match_path("/users/{id}/orders", "/users/42/orders") == {"id": "42"}
    assert match_path("/users/42", "/users/43") is None
    assert match_path("/users/{id}", "/users/a/b") is None      # 段数不一致
    assert match_path("/users", "/users/") == {}                # 尾斜杠归一


def test_method_and_enabled_gate():
    r = _rule(method="POST")
    assert rule_matches(r, "GET", "/users/1", {}, {}, b"") is None
    r2 = _rule(enabled=False)
    assert rule_matches(r2, "GET", "/users/1", {}, {}, b"") is None


def test_query_condition_eq_and_regex():
    r_eq = _rule(conditions=[{"scope": "query", "key": "version", "match": "eq", "value": "2"}])
    assert rule_matches(r_eq, "GET", "/users/1", {"version": ["2"]}, {}, b"") == {"id": "1"}
    assert rule_matches(r_eq, "GET", "/users/1", {"version": ["1"]}, {}, b"") is None
    r_re = _rule(conditions=[{"scope": "query", "key": "version", "match": "regex", "value": "^v[0-9]+$"}])
    assert rule_matches(r_re, "GET", "/users/1", {"version": ["v2"]}, {}, b"") is not None
    assert rule_matches(r_re, "GET", "/users/1", {"version": ["x2"]}, {}, b"") is None
    r_bad_re = _rule(conditions=[{"scope": "query", "key": "v", "match": "regex", "value": "("}])
    assert rule_matches(r_bad_re, "GET", "/users/1", {"v": ["x"]}, {}, b"") is None  # 非法正则不抛


def test_header_condition_case_insensitive_key():
    r = _rule(conditions=[{"scope": "header", "key": "X-Version", "match": "eq", "value": "2"}])
    assert rule_matches(r, "GET", "/users/1", {}, {"x-version": ["2"]}, b"") is not None


def test_body_condition_jsonpath_typed_and_invalid_json():
    r_num = _rule(method="POST", path="/x", conditions=[{"scope": "body", "key": "$.user.id", "match": "eq", "value": "123"}])
    body = b'{"user": {"id": 123}}'
    assert rule_matches(r_num, "POST", "/x", {}, {}, body) is not None
    assert rule_matches(r_num, "POST", "/x", {}, {}, b'{"user": {"id": 124}}') is None
    assert rule_matches(r_num, "POST", "/x", {}, {}, b"not-json") is None   # 非法 JSON 跳过
    r_str = _rule(path="/x", conditions=[{"scope": "body", "key": "$.name", "match": "eq", "value": "王"}])
    assert rule_matches(r_str, "GET", "/x", {}, {}, '{"name": "王"}'.encode()) is not None
    r_bool = _rule(path="/x", conditions=[{"scope": "body", "key": "$.flag", "match": "eq", "value": "true"}])
    assert rule_matches(r_bool, "GET", "/x", {}, {}, b'{"flag": true}') is not None
    r_missing = _rule(path="/x", conditions=[{"scope": "body", "key": "$.nope", "match": "eq", "value": "1"}])
    assert rule_matches(r_missing, "GET", "/x", {}, {}, b'{"a": 1}') is None  # 无节点不成立
    r_badpath = _rule(path="/x", conditions=[{"scope": "body", "key": "$$bad", "match": "eq", "value": "1"}])
    assert rule_matches(r_badpath, "GET", "/x", {}, {}, b'{"a": 1}') is None  # 非法 JSONPath 不抛


def test_conditions_are_and_and_pick_first_match():
    r1 = _rule(conditions=[{"scope": "query", "key": "a", "match": "eq", "value": "1"},
                           {"scope": "query", "key": "b", "match": "eq", "value": "2"}])
    assert rule_matches(r1, "GET", "/users/1", {"a": ["1"]}, {}, b"") is None      # 缺 b → 不命中
    r_late = _rule(path="/users/{id}")
    r_first = _rule(path="/users/special")
    got, vars_ = pick_rule([r_first, r_late], "GET", "/users/special", {}, {}, b"")
    assert got is r_first and vars_ == {}
    got2, _ = pick_rule([r_first, r_late], "GET", "/users/42", {}, {}, b"")
    assert got2 is r_late
    got3, _ = pick_rule([], "GET", "/x", {}, {}, b"")
    assert got3 is None
