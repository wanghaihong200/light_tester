# tests/test_ui_dsl.py
from app.ui_automation import dsl, events


def test_render_text():
    assert dsl.render_text("{{u}}-{{p}}", {"u": "a", "p": "b"}) == "a-b"
    assert dsl.render_text("{{missing}}", {}) == "{{missing}}"  # 未定义原样保留
    assert dsl.render_text("plain", {}) == "plain"


def test_validate_script():
    ok = {"version": 1, "meta": {}, "variables": [], "steps": [
        {"id": "s1", "action": "click", "locator": {"strategy": "css", "value": "#a"}}]}
    assert dsl.validate_script(ok) == []
    bad = {"version": 2, "steps": [{"id": "s1", "action": "fly"}]}
    errs = dsl.validate_script(bad)
    assert any("version" in e for e in errs) and any("fly" in e for e in errs)
    miss = {"version": 1, "steps": [{"id": "s1", "action": "fill", "locator": {"strategy": "css", "value": "#u"}}]}
    assert any("text" in e for e in dsl.validate_script(miss))  # fill 缺 params.text


def test_dedupe_input_then_click():
    tgt = {"id": "user", "tag": "input", "type": "text"}
    raw = [
        {"kind": "input", "target": tgt, "value": "a"},
        {"kind": "input", "target": tgt, "value": "ab"},   # 连续输入合并
        {"kind": "click", "target": {"id": "go", "tag": "button", "text": "go"}},
    ]
    steps = events.dedupe_and_map(raw)
    assert [s["action"] for s in steps] == ["fill", "click"]
    assert steps[0]["params"]["text"] == "ab"


def test_map_enter_and_goto_and_change():
    raw = [
        {"kind": "goto", "url": "https://x.com"},
        {"kind": "input", "target": {"id": "q", "tag": "input"}, "value": "kw"},
        {"kind": "keydown", "target": {"id": "q", "tag": "input"}, "key": "Enter"},
        {"kind": "change", "target": {"id": "sel", "tag": "select"}, "value": "2"},
    ]
    steps = events.dedupe_and_map(raw)
    assert [s["action"] for s in steps] == ["goto", "fill", "press", "select_option"]
    assert steps[2]["params"]["key"] == "Enter"


def test_step_summary_and_locator_candidates():
    step = {"id": "s", "action": "click", "locator": {"strategy": "role", "role": "button", "name": "登录", "fallbacks": [{"strategy": "css", "value": "#b"}]}}
    assert events.step_summary(step) == "点击 登录"
    cands = dsl.raw_locator_candidates(step["locator"])
    assert cands == [step["locator"], {"strategy": "css", "value": "#b"}]


# ---------- 以下为补充边界用例 ----------

def test_render_text_edge_cases():
    # 花括号内允许空白
    assert dsl.render_text("{{ u }}", {"u": "x"}) == "x"
    # 非字符串值原样返回
    assert dsl.render_text(123, {}) == 123
    # 变量值非字符串时转成 str
    assert dsl.render_text("n={{n}}", {"n": 7}) == "n=7"


def test_validate_script_more_cases():
    # 空 steps 合法
    assert dsl.validate_script({"version": 1, "steps": []}) == []
    # click 缺 locator
    errs = dsl.validate_script({"version": 1, "steps": [{"id": "s1", "action": "click"}]})
    assert any("locator" in e for e in errs)
    # wait 缺 ms / ms 非整数
    assert any("params.ms" in e for e in dsl.validate_script(
        {"version": 1, "steps": [{"id": "s1", "action": "wait"}]}))
    assert any("ms 必须是整数" in e for e in dsl.validate_script(
        {"version": 1, "steps": [{"id": "s1", "action": "wait", "params": {"ms": "100"}}]}))
    # 变量名非法(数字开头 / 空名)
    errs = dsl.validate_script({"version": 1, "steps": [],
                                "variables": [{"name": "1bad"}, {"name": ""}]})
    assert len(errs) == 2
    # doc 缺 steps / variables 键也不抛异常
    assert dsl.validate_script({}) != []


def test_raw_locator_candidates_filters_unknown_strategy():
    loc = {"strategy": "xpath", "value": "//a", "fallbacks": [
        {"strategy": "css", "value": "#a"}, {"strategy": "nope", "value": "x"}]}
    assert dsl.raw_locator_candidates(loc) == [{"strategy": "css", "value": "#a"}]


def test_dedupe_edge_cases():
    tgt = {"id": "user", "tag": "input", "type": "text"}
    # 输入后点击同一元素:只保留 fill,不产生 click
    steps = events.dedupe_and_map([
        {"kind": "input", "target": tgt, "value": "v"},
        {"kind": "click", "target": tgt},
    ])
    assert [s["action"] for s in steps] == ["fill"]
    # 非功能键(如普通字母)不产生 press 步骤
    steps = events.dedupe_and_map([
        {"kind": "keydown", "target": tgt, "key": "a"},
    ])
    assert steps == []
    # 切换到另一元素输入:先 flush 前一个 fill
    other = {"id": "pwd", "tag": "input", "type": "password"}
    steps = events.dedupe_and_map([
        {"kind": "input", "target": tgt, "value": "1"},
        {"kind": "input", "target": other, "value": "2"},
    ])
    assert [s["action"] for s in steps] == ["fill", "fill"]
    assert [s["params"]["text"] for s in steps] == ["1", "2"]
    # select_option 的 value 统一转字符串
    steps = events.dedupe_and_map([
        {"kind": "change", "target": {"id": "sel", "tag": "select"}, "value": 3},
    ])
    assert steps[0]["params"]["value"] == "3"


def test_validate_script_bad_params():
    # params 为 null:视同缺参,返回错误而非崩溃
    errs = dsl.validate_script({"version": 1, "steps": [
        {"id": "s1", "action": "fill", "locator": {"strategy": "css", "value": "#u"}, "params": None}]})
    assert any("params.text" in e for e in errs)
    # params 为字符串:报类型错误,不抛 AttributeError
    errs = dsl.validate_script({"version": 1, "steps": [
        {"id": "s1", "action": "fill", "locator": {"strategy": "css", "value": "#u"}, "params": "oops"}]})
    assert any("params 必须是对象" in e for e in errs)
    # 合法脚本仍返回空列表
    ok = {"version": 1, "steps": [{"id": "s1", "action": "click", "locator": {"strategy": "css", "value": "#a"}}]}
    assert dsl.validate_script(ok) == []


def test_validate_script_malformed_containers():
    # steps 为字符串:报类型错误而非遍历字符
    assert any("steps 必须是数组" in e for e in dsl.validate_script({"version": 1, "steps": "x"}))
    # steps 项非对象:跳过该步检查并报错
    assert any("步骤1" in e for e in dsl.validate_script({"version": 1, "steps": ["x"]}))
    # variables 为字符串 / 变量项非对象 / 变量名非字符串
    assert any("variables 必须是数组" in e
               for e in dsl.validate_script({"version": 1, "steps": [], "variables": "x"}))
    assert any("变量必须是对象" in e
               for e in dsl.validate_script({"version": 1, "steps": [], "variables": ["x"]}))
    assert any("变量名非法" in e
               for e in dsl.validate_script({"version": 1, "steps": [], "variables": [{"name": 123}]}))
    # doc 本身非对象:返回错误列表而非抛 AttributeError
    assert dsl.validate_script("nope") == ["脚本必须是对象"]
    # steps / variables 键缺失仍合法
    assert dsl.validate_script({"version": 1}) == []


def test_non_functional_key_keeps_input_pending():
    tgt = {"id": "user", "tag": "input", "type": "text"}
    # Shift(输大写字母必然出现)不应打断同元素的输入合并
    steps = events.dedupe_and_map([
        {"kind": "input", "target": tgt, "value": "h"},
        {"kind": "keydown", "target": tgt, "key": "Shift"},
        {"kind": "input", "target": tgt, "value": "hH"},
    ])
    assert [s["action"] for s in steps] == ["fill"]
    assert steps[0]["params"]["text"] == "hH"
    # 功能键仍打断合并并产生 press(行为不回退)
    steps = events.dedupe_and_map([
        {"kind": "input", "target": tgt, "value": "a"},
        {"kind": "keydown", "target": tgt, "key": "Enter"},
    ])
    assert [s["action"] for s in steps] == ["fill", "press"]


def test_finalize_steps_and_target_to_locator():
    # goto 无 target,不产 locator
    out = events.finalize_steps([{"id": "s1", "action": "goto", "params": {"url": "https://x.com"}}])
    assert out == [{"id": "s1", "action": "goto", "params": {"url": "https://x.com"}}]
    # 仅 text 无 aria_label 的 role target:name 取 text(KeyError 回归)
    loc = events.target_to_locator({"tag": "button", "role": "button", "text": "登录"})
    assert loc["name"] == "登录"
    # test_id 优先作为 primary
    loc = events.target_to_locator({"tag": "input", "test_id": "username", "id": "u"})
    assert loc["strategy"] == "test_id" and loc["value"] == "username"
    assert loc["fallbacks"] == [{"strategy": "css", "value": "#u"}]
    # 无 test_id 时用 id 生成 css,且无 fallbacks 键
    loc = events.target_to_locator({"tag": "input", "id": "u"})
    assert loc == {"strategy": "css", "value": "#u"}
    # input 无 id 有 name → tag[name='...']
    loc = events.target_to_locator({"tag": "input", "name": "q"})
    assert loc == {"strategy": "css", "value": "input[name='q']"}
    # 都没有 → 裸 tag
    loc = events.target_to_locator({"tag": "div"})
    assert loc == {"strategy": "css", "value": "div"}
    # finalize 后步骤可被 validate 通过
    raw = [
        {"id": "s1", "action": "goto", "params": {"url": "https://x.com"}},
        {"id": "s2", "action": "click", "target": {"tag": "button", "role": "button", "text": "登录"}},
    ]
    doc = {"version": 1, "variables": [], "steps": events.finalize_steps(raw)}
    assert dsl.validate_script(doc) == []


def test_step_summary_more_actions():
    assert events.step_summary({"action": "goto", "params": {"url": "https://x.com"}}) == "打开 https://x.com"
    assert events.step_summary({"action": "wait", "params": {"ms": 1000}}) == "等待 1000ms"
    assert events.step_summary({"action": "press", "params": {"key": "Enter"}}) == "按键 Enter"
    assert events.step_summary({"action": "fill", "locator": {"strategy": "css", "value": "#u"}, "params": {"text": "admin"}}) == "输入 #u=admin"
    assert events.step_summary({"action": "select_option", "locator": {"strategy": "css", "value": "#s"}, "params": {"value": "2"}}) == "选择 #s=2"
    assert events.step_summary({"action": "set_var", "params": {"name": "t", "value": "1"}}) == "设变量 t=1"
    assert events.step_summary({"action": "assert_visible", "locator": {"strategy": "css", "value": "#a"}}) == "断言 可见 #a"
    assert events.step_summary({"action": "assert_exists", "locator": {"strategy": "css", "value": "#a"}}) == "断言 存在 #a"
    assert events.step_summary({"action": "assert_text", "params": {"text": "欢迎"}}) == "断言 文本包含 欢迎"
    assert events.step_summary({"action": "assert_text", "params": {"text": "欢迎", "mode": "equals"}}) == "断言 文本等于 欢迎"
    # 未知 action 原样返回 action 名
    assert events.step_summary({"action": "mystery"}) == "mystery"
