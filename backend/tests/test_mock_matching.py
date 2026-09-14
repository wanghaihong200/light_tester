"""匹配引擎:路径模板/条件 AND/JSONPath/正则/组序→组内序首条命中。"""
from types import SimpleNamespace as NS

from app.mock_service import matching
from app.mock_service.matching import match_path, validate_path_template


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


def _group(method="GET", path="/a/{id}", enabled=True, **kw):
    return NS(method=method, path_template=path, enabled=enabled, **kw)


def _rule(conditions=None, enabled=True, **kw):
    return NS(conditions=conditions or [], enabled=enabled, **kw)


def _pick(groups_pair, method="GET", path="/a/1", query=None, headers=None, body=b""):
    return matching.pick_rule(groups_pair, method, path, query or {}, headers or {}, body)


def test_pick_rule_group_order_then_rule_order():
    """组序→组内序:前组命中即短路,后组同路由也不看;组内按序首条命中。"""
    g1, g2 = _group(), _group()
    r12, r11 = _rule(), _rule()          # g1 内:规则2 排前
    hit = _pick([(g1, [r12, r11]), (g2, [_rule()])])
    assert hit == (r12, g1, {"id": "1"})


def test_pick_rule_disabled_group_skipped_whole():
    """组级停用=整组跳过,组内规则再能中也不算。"""
    g1, g2 = _group(enabled=False), _group(path="/b")
    r1, r2 = _rule(), _rule()
    rule, group, _ = _pick([(g1, [r1]), (g2, [r2])], path="/b")
    assert rule is r2 and group is g2


def test_pick_rule_disabled_rule_skipped_in_group():
    """组内停用规则跳过,下一条仍可命中。"""
    g = _group()
    r1, r2 = _rule(enabled=False), _rule()
    rule, group, _ = _pick([(g, [r1, r2])])
    assert rule is r2 and group is g


def test_pick_rule_conditions_gate_within_group():
    """同组条件变体:条件不满足顺延下一条,全不满足=组未命中。"""
    g = _group()
    conds = [{"scope": "query", "key": "v", "match": "eq", "value": "2"}]
    r_v2, r_any = _rule(conds), _rule()
    rule, _, _ = _pick([(g, [r_v2, r_any])], path="/a/1", query={"v": ["1"]})
    assert rule is r_any                  # 第一条条件不过,落到组内第二条
    rule, _, _ = _pick([(g, [r_v2])], path="/a/1", query={"v": ["2"]})
    assert rule is r_v2


def test_pick_rule_none_when_all_groups_miss():
    rule, group, path_vars = _pick([(_group(), [_rule()])], path="/zzz")
    assert rule is None and group is None and path_vars == {}


def test_route_matches():
    assert matching.route_matches(_group(), "GET", "/a/9") is True
    assert matching.route_matches(_group(), "POST", "/a/9") is False
    assert matching.route_matches(_group(), "GET", "/b/9") is False


# ---------- DEFER 演进批次:#108 _cond_ok 分支回归锚(计划15 重构时随旧用例遗失) ----------

def test_cond_ok_header_name_case_insensitive():
    """锚1:header 名大小写不敏感(引擎内部 headers.get(key.lower()))。"""
    cond = {"scope": "header", "key": "X-Trace", "match": "eq", "value": "t1"}
    assert matching._cond_ok(cond, {}, {"x-trace": ["t1"]}, b"") is True
    assert matching._cond_ok(cond, {}, {"x-other": ["t1"]}, b"") is False


def test_cond_ok_body_jsonpath_typed_match():
    """锚2:JSONPath 期望值按 JSON 字面解析,类型必须一致(数字 1 ≠ 字符串 "1")。"""
    doc = b'{"flag": true, "n": 1}'
    assert matching._cond_ok({"scope": "body", "key": "$.flag", "match": "eq", "value": "true"}, {}, {}, doc)
    assert matching._cond_ok({"scope": "body", "key": "$.n", "match": "eq", "value": "1"}, {}, {}, doc)
    # 类型锚:number 1 不匹配 JSON 引号串 "1"
    assert not matching._cond_ok({"scope": "body", "key": "$.n", "match": "eq", "value": '"1"'}, {}, {}, doc)


def test_cond_ok_bad_regex_is_false_not_raise():
    """锚3:非法正则=条件不成立(False),不抛 500。"""
    cond = {"scope": "query", "key": "v", "match": "regex", "value": "([bad"}
    assert matching._cond_ok(cond, {"v": ["x"]}, {}, b"") is False


# ---------- DEFER 演进批次:#109 组内全不中→续看下一组(用户拍板钉现语义,2026-09-14) ----------

def test_pick_rule_group_route_hit_but_rules_all_miss_continues_to_next_group():
    """组路由命中但组内规则全不中时,外层循环不终止,续看下一个路由命中的组。
    仅模板重叠场景可观测:GET /a/{id} 与 GET /a/special 对 /a/special 请求双命中
    (重路校验只挡完全相同 method+path_template,挡不住模板重叠)。"""
    g_a = _group(path="/a/{id}")            # 组序在前,规则条件全不中
    g_b = _group(path="/a/special")
    r_a = _rule([{"scope": "query", "key": "v", "match": "eq", "value": "x"}])
    r_b = _rule()
    rule, group, captured = _pick([(g_a, [r_a]), (g_b, [r_b])], path="/a/special")
    assert rule is r_b and group is g_b and captured == {}
