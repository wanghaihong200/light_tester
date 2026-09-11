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
