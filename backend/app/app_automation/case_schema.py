"""SoloPi 原生用例 JSON 校验(纯函数)。字段事实源 = 前置研究第 2 节(Harness 分支源码一手核实)。
校验哲学:只挡「确定非法」——缺顶层必填/含导入器管理字段/steps 非空数组/步骤缺 actionEnum/
参数值非字符串/内部运行时动作(IF/WHILE 系,CLI 编写/导入/回放一律拒)/ASSERT 缺断言参数;
动作白名单不穷举(100+ 动作随分支演进);高危动作单独盘点供执行前显式确认。"""
import json

TOP_REQUIRED = ("caseName", "targetAppPackage")
FORBIDDEN_TOP = ("id", "gmtCreate", "gmtModify", "selected", "caseFingerprint", "storePath")
INTERNAL_ACTIONS = ("IF", "WHILE", "CONTINUE", "BREAK")
HIGH_RISK_ACTIONS = ("CLEAR_DATA", "KILL_PROCESS", "JUMP_TO_PAGE")
_STRING_ASSERT_MODES = ("assert_accurate", "assert_contain", "assert_regular")


def _steps(case: dict) -> list:
    log = case.get("operationLog")
    return (log or {}).get("steps") or []


def validate_case(case: dict) -> list[str]:
    if not isinstance(case, dict):
        return ["用例必须是 JSON 对象"]
    errs: list[str] = []
    for key in FORBIDDEN_TOP:
        if key in case:
            errs.append(f"顶层禁止字段 {key}(由导入器管理,请删除)")
    for key in TOP_REQUIRED:
        v = case.get(key)
        if not isinstance(v, str) or not v.strip():
            errs.append(f"缺少必填顶层字段 {key}")
    if not isinstance(case.get("operationLog"), dict) or not _steps(case):
        errs.append("operationLog.steps 必须是非空数组")
        return errs
    for i, st in enumerate(_steps(case), 1):
        prefix = f"步骤{i}"
        if not isinstance(st, dict):
            errs.append(f"{prefix}: 必须是对象")
            continue
        method = st.get("operationMethod")
        if not isinstance(method, dict) or not str(method.get("actionEnum") or "").strip():
            errs.append(f"{prefix}: operationMethod.actionEnum 缺失")
            continue
        action = method["actionEnum"]
        if action in INTERNAL_ACTIONS:
            errs.append(f"{prefix}: {action} 是录制运行时内部动作,CLI 编写/导入/回放一律拒绝,平台不支持")
        params = method.get("operationParam")
        if params is not None and not isinstance(params, dict):
            errs.append(f"{prefix}: operationParam 必须是对象")
        elif isinstance(params, dict):
            bad = sorted(k for k, v in params.items() if not isinstance(v, str))
            if bad:
                errs.append(f"{prefix}: 参数值必须全为字符串({','.join(bad)})")
        if action == "ASSERT":
            p = params if isinstance(params, dict) else {}
            if "assertMode" not in p or "assertInputContent" not in p:
                errs.append(f"{prefix}: ASSERT 需要 assertMode + assertInputContent")
        node = st.get("operationNode")
        if node is not None and not isinstance(node, dict):
            errs.append(f"{prefix}: operationNode 必须是对象或 null")
    return errs


def high_risk_actions(case: dict) -> list[str]:
    """用例内出现的高危动作去重排序(执行需显式确认,后端向 CLI 传 --confirm-high-risk)。"""
    found = {st["operationMethod"]["actionEnum"] for st in _steps(case) if isinstance(st, dict)
             and isinstance(st.get("operationMethod"), dict)
             and st["operationMethod"].get("actionEnum") in HIGH_RISK_ACTIONS}
    return sorted(found)


_RECORD_TOP_KEYS = ("caseName", "caseDesc", "targetAppPackage", "targetAppLabel",
                    "recordMode", "advanceSettings", "priority")


def normalize_case(raw: dict) -> dict:
    """RecordCaseInfo 包装结构 → 原生用例;原生 dict 恒等返回。
    包装判据 = operationLog 是 str:手机 App 回放列表「导出用例」写 /sdcard/solopi/export 的
    文件(真机实测)顶层另带 id/gmtCreate/gmtModify/selected/storePath,operationLog 是内嵌
    GeneralOperationLogBean JSON 字符串({"steps":[…], "storePath":…}),原样过不了 validate_case
    的禁字段闸。归一化只保留业务顶层键 + {"steps": …};包装层管理字段与内嵌 storePath 一律丢弃;
    operationLog 非 str(原生/harness 推送文件)恒等;operationLog 字符串解析失败抛 ValueError。"""
    if not isinstance(raw, dict):
        raise ValueError("用例必须是 JSON 对象")
    log = raw.get("operationLog")
    if not isinstance(log, str):
        return raw
    try:
        inner = json.loads(log)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(f"operationLog 内嵌 JSON 解析失败: {e}") from e
    if not isinstance(inner, dict) or not isinstance(inner.get("steps"), list):
        raise ValueError("operationLog 内嵌 JSON 须为含 steps 数组的对象")
    out = {k: raw[k] for k in _RECORD_TOP_KEYS if k in raw}
    out["operationLog"] = {"steps": inner["steps"]}
    return out
