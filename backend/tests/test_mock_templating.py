"""模板渲染:上下文/辅助函数/未定义空串/非模板原文。"""
from app.mock_service.templating import render_template


def _render(tpl, **kw):
    kw.setdefault("path_vars", {})
    kw.setdefault("query", {})
    kw.setdefault("headers", {})
    kw.setdefault("body_json", None)
    return render_template(tpl, **kw)


def test_context_path_query_header_body():
    out = _render('{"id": "{{ path.id }}"}', path_vars={"id": "42"})
    assert out == '{"id": "42"}'
    out2 = _render('{{ query.version }}', query={"version": ["2"]})
    assert out2 == "2"
    out3 = _render('{{ header["content-type"] }}', headers={"content-type": ["application/json"]})
    assert out3 == "application/json"
    out4 = _render('{{ body.user.name }}', body_json={"user": {"name": "王"}})
    assert out4 == "王"


def test_helpers_uuid_now_rand_jpath():
    u = _render("{{ uuid4() }}")
    assert len(u) == 36 and u.count("-") == 4
    ts = int(_render("{{ now_ts() }}"))
    import time
    assert abs(ts - time.time()) < 60
    r = int(_render("{{ rand_int(1, 3) }}"))
    assert 1 <= r <= 3
    assert _render("{{ jpath('$.a.b') }}", body_json={"a": {"b": "x"}}) == "x"
    assert _render("{{ jpath('$.a') }}", body_json={"a": {"b": 1}}) == '{"b": 1}'
    assert _render("{{ jpath('$.nope') }}", body_json={}) == ""


def test_undefined_renders_empty_and_plain_text_passthrough():
    assert _render("{{ nope }}") == ""
    assert _render("hello world") == "hello world"
    assert _render("{{ path.id }}", path_vars={}) == ""    # 不抛未定义错误


def test_undefined_chained_access_renders_empty():
    # 链式取值(属性/下标)同样渲染空串,不抛 UndefinedError(契约:未定义不抛错)
    assert _render("{{ nope.foo }}") == ""
    assert _render("{{ body.user.name }}", body_json=None) == ""
    assert _render("{{ body['a']['b'] }}", body_json={}) == ""


def test_sandbox_blocks_attribute_escape():
    """沙箱:下划线属性(__class__/__mro__/__subclasses__)被拦截 → 渲染空串。

    修复前是裸 Environment,`{{ ''.__class__ }}` 会渲染出 `<class 'str'>`
    泄漏类对象(可沿 __mro__.__subclasses__ 打穿子进程);沙箱下安全未定义渲染空串,
    渲染不抛异常。四个辅助函数是传入 callable,沙箱内照常可用(见上方用例)。"""
    out = _render("{{ ''.__class__ }}")
    assert out == "" and "class" not in out
    deep = _render("{{ ''.__class__.__mro__[1].__subclasses__ }}")
    assert deep == "" and "subclasses" not in deep
    tpl_escape = _render("{{ ().__class__.__bases__[0].__subclasses__ }}")
    assert tpl_escape == ""
