# backend/tests/test_appium_export.py
import ast

from app.app_automation.appium_export import collect_export_bundle, render_steps, slugify


def _node(rid=None, text=None, desc=None, xpath=None):
    return {"resourceId": rid, "text": text, "description": desc, "xpath": xpath,
            "className": "android.widget.Button", "nodeBound": [0, 0, 1, 1]}


def _step(action, params=None, node=None, idx=0):
    return {"operationNode": node,
            "operationMethod": {"actionEnum": action, "operationParam": params or {},
                                "encrypt": False, "safeEncrypt": False},
            "operationIndex": idx, "operationId": "g1", "stepId": f"s{idx}"}


PKG = "com.example.shop"


def test_slugify():
    s = slugify(3, "下单流程")
    assert s.startswith("3_") and ("_" not in s[2:] or s == "3_case")  # 拼音串内不塌陷为多段
    assert slugify(7, "Order Pay!!") == "7_order_pay"
    assert slugify(7, "!!!") == "7_case"


def test_render_steps_core_actions():
    steps = [
        _step("CLICK", node=_node(rid="com.example.shop:id/btn_pay"), idx=0),
        _step("CLICK", node=_node(rid="btn_home"), idx=1),  # 短名自动补包名
        _step("INPUT", params={"text": "hello ${user}"}, node=_node(text="用户名"), idx=2),
        _step("SLEEP", params={"text": "800"}, idx=3),
        _step("LET", params={"allocKey": "user", "allocValue": "alice", "allocType": "1"}, idx=4),
        _step("ASSERT", params={"assertMode": "assert_contain", "assertInputContent": "支付成功"},
              node=_node(desc="pay-result"), idx=5),
        _step("ASSERT", params={"assertMode": "assert_accurate", "assertInputContent": "登录"},
              node=_node(text="登录"), idx=6),
    ]
    lines, errs = render_steps(steps, PKG)
    assert errs == []
    assert lines == [
        "    driver.find_element(AppiumBy.ID, 'com.example.shop:id/btn_pay').click()",
        "    driver.find_element(AppiumBy.ID, 'com.example.shop:id/btn_home').click()",
        "    driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text(\"用户名\")').clear()",
        "    driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text(\"用户名\")')"
        ".send_keys(f\"hello {_v('user')}\")",
        "    time.sleep(0.800)",
        "    PARAMS['user'] = 'alice'",
        "    assert '支付成功' in driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, "
        "'new UiSelector().description(\"pay-result\")').text",
        "    assert driver.find_element(AppiumBy.ANDROID_UIAUTOMATOR, 'new UiSelector().text(\"登录\")')"
        ".text == '登录'",
    ]


def test_long_click_and_unknown_rejected():
    lines, errs = render_steps([
        _step("LONG_CLICK", node=_node(rid="btn_x"), idx=0),
        _step("GESTURE", params={"gesturePath": "1,1;2,2"}, idx=1),
        _step("ASSERT_TOAST", params={"assertMode": "assert_contain", "assertInputContent": "已提交"}, idx=2),
    ], PKG)
    assert len(errs) == 2
    assert "步骤2" in errs[0] and "GESTURE" in errs[0]
    assert "步骤3" in errs[1] and "ASSERT_TOAST" in errs[1]
    assert any("longClickGesture" in ln for ln in lines)


def test_node_without_locator_rejected():
    _, errs = render_steps([_step("CLICK", node=_node(), idx=0)], PKG)
    assert errs and "定位" in errs[0]


def _case(steps):
    return {"caseName": "下单冒烟", "targetAppPackage": PKG, "operationLog": {"steps": steps}}


def test_bundle_structure_and_valid_python():
    case = _case([
        _step("LET", params={"allocKey": "user", "allocValue": "bob", "allocType": "1"}, idx=0),
        _step("CLICK", node=_node(rid="btn_go"), idx=1),
    ])
    b = collect_export_bundle(5, "下单冒烟", case)
    assert b.errors == []
    assert set(b.files) == {"test_5_xiadanmaoyan.py", "RUN.md"} or list(b.files)[0].startswith("test_5_")
    code = b.files["test_5_xiadanmaoyan.py"]
    ast.parse(code)  # 生成代码必须是合法 Python
    assert "PACKAGE = 'com.example.shop'" in code
    assert "def test_5_" in code
    assert "pytest" in b.files["RUN.md"] and "appium" in b.files["RUN.md"].lower()


def test_bundle_errors_no_files():
    case = _case([_step("JUMP_TO_PAGE", params={"scheme": "alipays://x"}, idx=0)])
    b = collect_export_bundle(9, "跳转", case)
    assert b.errors and b.files == {}
