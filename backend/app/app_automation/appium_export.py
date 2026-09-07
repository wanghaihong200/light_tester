"""SoloPi 原生用例 JSON → Python·pytest Appium 脚本翻译器(纯函数,零 IO)。
翻译范围(最小可用集,其余动作拒并列出步骤,与计划 11 ai 拒导同哲学):
  CLICK / LONG_CLICK / INPUT / CLICK_AND_INPUT / SLEEP / ASSERT(字符串三模式) / LET
节点定位映射:resourceId→AppiumBy.ID(短名自动补 targetAppPackage 前缀);
text/description→UiSelector().text()/description();xpath→AppiumBy.XPATH。
${var} → _v('var');断言 assert_accurate→==、assert_contain→in、assert_regular→re.search。
对照官方 SoloPi-Convertor 的映射方向;动作集合 = SUPPORTED,前端编辑器动作集与它对齐。"""
import re
from dataclasses import dataclass, field
from datetime import datetime

from pypinyin import lazy_pinyin

SUPPORTED = ("CLICK", "LONG_CLICK", "INPUT", "CLICK_AND_INPUT", "SLEEP", "ASSERT", "LET")

_VAR_RE = re.compile(r"\$\{([^}\s]+)\}")


@dataclass
class ExportBundle:
    files: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def slugify(script_id: int, name: str) -> str:
    text = "".join(lazy_pinyin(name or "")).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return f"{script_id}_{text or 'case'}"


_HEADER = '''"""由轻测试平台导出的 Appium 测试,来源脚本 #{script_id}「{script_name}」(导出于 {exported_at})。

依赖: pip install pytest appium-python-client
前置: 本机运行 Appium server(uiautomator2 driver),USB 连接 Android 设备。
环境变量: APPIUM_SERVER(默认 http://127.0.0.1:4723)/ DEVICE_UDID(adb serial,建议填)/ APP_ACTIVITY(可选,缺省由包默认 Activity 启动)。
运行: pytest {filename} -v
生成区为机器翻译,请勿手改进仓库的步骤代码;变量默认值在下方 PARAMS 中修改。
"""
import os
import re
import time

import pytest
from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

PARAMS = {{}}
PACKAGE = {package!r}


def _v(name: str) -> str:
    """取参数;未定义保留 ${{name}} 占位(与平台渲染语义一致)。"""
    return str(PARAMS.get(name, "${{" + name + "}}"))


@pytest.fixture
def driver():
    opts = UiAutomator2Options()
    opts.platform_name = "Android"
    udid = os.environ.get("DEVICE_UDID", "")
    if udid:
        opts.udid = udid
        opts.device_name = udid
    else:
        opts.device_name = "android"
    opts.app_package = PACKAGE
    activity = os.environ.get("APP_ACTIVITY", "")
    if activity:
        opts.app_activity = activity
    opts.no_reset = True  # 不清应用数据,复用设备上的登录态
    d = webdriver.Remote(os.environ.get("APPIUM_SERVER", "http://127.0.0.1:4723"), options=opts)
    d.activate_app(PACKAGE)
    yield d
    d.quit()
'''

_RUN_MD = '''# APP 自动化脚本运行说明(Appium)

本文件由轻测试平台「APP自动化」导出(来源脚本:#{script_id}「{script_name}」,用例名 {case_name})。

## 环境准备

```bash
pip install pytest appium-python-client
appium --use-plugins=images  # 仅示例;正常启动: appium
```

## 运行

```bash
export DEVICE_UDID=<adb serial>          # 建议显式指定设备
export APP_ACTIVITY=<可选,主 Activity>
pytest {filename} -v
```

## 变量

脚本顶部 `PARAMS` 字典即参数表,改值即可;`${{name}}` 占位在未定义时原样保留。
'''


def _py_str(s: str) -> str:
    return repr(str(s))


def _interpolate(value: str) -> str:
    """${var} → f-string 的 _v('var');无变量返回 repr 字面量。"""
    value = str(value)
    if not _VAR_RE.search(value):
        return _py_str(value)
    body = _VAR_RE.sub(lambda m: "{_v('" + m.group(1) + "')}", value)
    return "f" + repr(body)


def render_find(node: dict, package: str) -> str:
    """operationNode → driver.find_element(<参数串>);resourceId 短名自动补包名。"""
    rid, text, desc, xpath = node.get("resourceId"), node.get("text"), node.get("description"), node.get("xpath")
    if rid:
        full = str(rid) if ":id/" in str(rid) else f"{package}:id/{rid}"
        return f"AppiumBy.ID, {_py_str(full)}"
    if text:
        return f"AppiumBy.ANDROID_UIAUTOMATOR, {_py_str(f'new UiSelector().text(\"{text}\")')}"
    if desc:
        return f"AppiumBy.ANDROID_UIAUTOMATOR, {_py_str(f'new UiSelector().description(\"{desc}\")')}"
    if xpath:
        return f"AppiumBy.XPATH, {_py_str(xpath)}"
    raise ValueError("节点缺少可定位字段(resourceId/text/description/xpath)")


def render_steps(steps: list[dict], package: str, indent: str = "    ") -> tuple[list[str], list[str]]:
    lines: list[str] = []
    errs: list[str] = []
    for idx, st in enumerate(steps, 1):
        method = (st.get("operationMethod") or {}) if isinstance(st, dict) else {}
        action = str(method.get("actionEnum") or "")
        params = method.get("operationParam") or {}
        node = st.get("operationNode")
        try:
            if action not in SUPPORTED:
                raise ValueError(f"动作 {action or '(空)'} 平台不翻译(支持范围: {'/'.join(SUPPORTED)})")
            if action in ("CLICK", "LONG_CLICK", "INPUT", "CLICK_AND_INPUT", "ASSERT") and not isinstance(node, dict):
                raise ValueError(f"{action} 需要 operationNode")
            find = f"driver.find_element({render_find(node, package)})" if isinstance(node, dict) else ""
            if action == "CLICK":
                lines.append(f"{indent}{find}.click()")
            elif action == "LONG_CLICK":
                lines.append(f"{indent}_el = {find}")
                lines.append(f"{indent}driver.execute_script('mobile: longClickGesture', {{'elementId': _el.id}})")
            elif action in ("INPUT", "CLICK_AND_INPUT"):
                lines.append(f"{indent}{find}.clear()")
                lines.append(f"{indent}{find}.send_keys({_interpolate(params.get('text', ''))})")
            elif action == "SLEEP":
                lines.append(f"{indent}time.sleep({float(params.get('text') or 1000) / 1000:.3f})")
            elif action == "LET":
                lines.append(f"{indent}PARAMS[{_py_str(params.get('allocKey', ''))}] = "
                             f"{_interpolate(params.get('allocValue', ''))}")
            elif action == "ASSERT":
                mode = params.get("assertMode")
                want = _interpolate(params.get("assertInputContent", ""))
                if mode == "assert_accurate":
                    lines.append(f"{indent}assert {find}.text == {want}")
                elif mode == "assert_contain":
                    lines.append(f"{indent}assert {want} in {find}.text")
                else:  # assert_regular 及数值模式一律按正则表达(原样保真)
                    lines.append(f"{indent}assert re.search({want}, {find}.text)")
        except (KeyError, ValueError, TypeError) as e:
            errs.append(f"步骤{idx}: {e}")
    return lines, errs


def collect_export_bundle(script_id: int, script_name: str, case: dict) -> ExportBundle:
    """整条用例 → {test_*.py, RUN.md};有错误不产文件。"""
    bundle = ExportBundle()
    steps = ((case.get("operationLog") or {}).get("steps")) or []
    package = str(case.get("targetAppPackage") or "")
    body, errs = render_steps(steps, package)
    if errs:
        bundle.errors = errs
        return bundle
    fn = slugify(script_id, script_name)
    filename = f"test_{fn}.py"
    code = _HEADER.format(script_id=script_id, script_name=script_name,
                          exported_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                          filename=filename, package=package)
    code += f"\n\ndef test_{fn}(driver):\n" + ("\n".join(body) if body else "    pass") + "\n"
    bundle.files[filename] = code
    bundle.files["RUN.md"] = _RUN_MD.format(script_id=script_id, script_name=script_name,
                                            case_name=case.get("caseName") or script_name,
                                            filename=filename)
    return bundle
