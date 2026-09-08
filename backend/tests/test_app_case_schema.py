# backend/tests/test_app_case_schema.py
import json

import pytest

from app.app_automation.case_schema import high_risk_actions, normalize_case, validate_case


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


# ---- normalize_case:App「导出用例」RecordCaseInfo 包装结构 → 原生用例(真机实测校正)----

def _wrapped(steps=None, **over):
    """手机 App 回放列表「导出用例」写的包装结构:顶层多 id/gmtCreate/gmtModify/selected/storePath,
    operationLog 是内嵌 GeneralOperationLogBean JSON 字符串({"steps":[…], "storePath":…})。"""
    inner_steps = steps if steps is not None else [_step(), _step(action="CLICK", params={"text": ""})]
    raw = {"caseName": "App导出用例", "caseDesc": "回放列表导出", "targetAppPackage": "com.example.app",
           "targetAppLabel": "示例App", "recordMode": 1, "advanceSettings": {}, "priority": 0,
           "id": 7, "gmtCreate": "2026-09-08 10:00:00", "gmtModify": "2026-09-08 10:00:00",
           "selected": True, "storePath": "/sdcard/solopi/store/smoke",
           "operationLog": json.dumps({"steps": inner_steps,
                                       "storePath": "/sdcard/solopi/store/smoke"})}
    raw.update(over)
    return raw


def test_normalize_wrapped_record_case_to_native():
    out = normalize_case(_wrapped())
    assert isinstance(out["operationLog"], dict)
    assert len(out["operationLog"]["steps"]) == 2
    assert out["caseName"] == "App导出用例"
    assert out["targetAppPackage"] == "com.example.app"
    # 包装层 id/gmtCreate/gmtModify/selected/storePath 一律丢弃(operationLog 字符串已换成 dict)
    for bad in ("id", "gmtCreate", "gmtModify", "selected", "storePath"):
        assert bad not in out
    # 剥包装后过原生校验(禁字段闸 + steps 非空数组)
    assert validate_case(out) == []


def test_normalize_wrapped_bad_operation_log_raises():
    raw = _wrapped()
    raw["operationLog"] = "{not json"
    with pytest.raises(ValueError):
        normalize_case(raw)


def test_normalize_native_dict_identity():
    case = _case(id=1)  # 原生(harness/手贴)恒等返回,禁字段交由 validate_case 继续把守
    assert normalize_case(case) is case


def test_normalize_non_dict_raises():
    for bad in (None, "x", 3, [1]):
        with pytest.raises(ValueError):
            normalize_case(bad)
