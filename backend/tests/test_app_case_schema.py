# backend/tests/test_app_case_schema.py
from app.app_automation.case_schema import high_risk_actions, validate_case


def _step(action="SLEEP", params=None, node=None):
    return {"operationNode": node,
            "operationMethod": {"actionEnum": action, "operationParam": params or {"text": "500"},
                                "encrypt": False, "safeEncrypt": False},
            "operationIndex": 0, "operationId": "g1", "stepId": "s1"}


def _case(steps=None, **over):
    case = {"caseName": "smoke", "targetAppPackage": "com.example.app",
            "operationLog": {"steps": steps if steps is not None else [_step()]}}
    case.update(over)
    return case


def test_valid_case_passes():
    assert validate_case(_case()) == []


def test_missing_required_top_fields():
    errs = validate_case({"operationLog": {"steps": [_step()]}})
    assert any("caseName" in e for e in errs)
    errs2 = validate_case(_case(targetAppPackage="  "))
    assert any("targetAppPackage" in e for e in errs2)


def test_forbidden_generated_fields():
    errs = validate_case(_case(id=1, caseFingerprint="abc", storePath="/x"))
    for key in ("id", "caseFingerprint", "storePath"):
        assert any(key in e for e in errs)


def test_steps_must_be_nonempty_list():
    assert validate_case(_case(steps=[]))
    assert any("steps" in e for e in validate_case({"caseName": "a", "targetAppPackage": "b"}))


def test_internal_actions_rejected():
    errs_if = validate_case(_case(steps=[_step(action="IF", params={"check": "assert::a==1", "scope": ""})]))
    assert any("IF" in e and "内部" in e for e in errs_if)
    errs_while = validate_case(_case(steps=[_step(action="WHILE", params={"check": "loop::i<3"})]))
    assert any("WHILE" in e for e in errs_while)


def test_param_values_must_be_strings():
    errs = validate_case(_case(steps=[_step(params={"text": 500})]))
    assert any("字符串" in e for e in errs)


def test_assert_requires_fields():
    ok = validate_case(_case(steps=[_step(action="ASSERT", node={"resourceId": "com.a:id/t"},
                                           params={"assertMode": "assert_contain", "assertInputContent": "欢迎"})]))
    assert ok == []
    errs = validate_case(_case(steps=[_step(action="ASSERT", node={"resourceId": "com.a:id/t"}, params={})]))
    assert any("assertMode" in e for e in errs)
    # assertMode 缺 operationNode 也在步骤层被挡(node 必须是对象或 null;ASSERT 定位依赖节点)——
    # 平台校验只挡「确定非法」,node 为 null 的 ASSERT 交由端上执行时报错,这里不拦。


def test_high_risk_actions_detected():
    steps = [_step(), _step(action="CLEAR_DATA", params={"text": ""}),
             _step(action="KILL_PROCESS", params={"text": "com.x"}),
             _step(action="CLEAR_DATA", params={"text": ""})]
    assert high_risk_actions(_case(steps=steps)) == ["CLEAR_DATA", "KILL_PROCESS"]
    assert high_risk_actions(_case()) == []
