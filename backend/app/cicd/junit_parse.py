"""JUnit XML 统一解析:pytest 内置 --junitxml 与 Maven surefire 产出同构,一解析器通吃两域。

报告口径:failure/error 都算 failed(message 保留前 2000 字);单次执行最多落 500 行用例,
超出截断(执行记录是可回看事实源,不是无限日志仓)。
解析用 defusedxml:产物 XML 是 Jenkins 侧外部输入,防 XXE/实体炸弹(stdlib ET 裸奔不安全)。
"""
import defusedxml.ElementTree as ET

_MAX_MESSAGE = 2000
_MAX_CASES = 500


def parse_junit_xml(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    for el in root.iter():  # surefire 产物可带默认 xmlns,把 {uri}tag 剥成 tag 再匹配
        el.tag = el.tag.rpartition("}")[2]
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    cases: list[dict] = []
    for suite in suites:
        for tc in suite.findall("testcase"):
            status, message = "passed", None
            for child in tc:
                if child.tag in ("failure", "error"):
                    status = "failed"
                    message = ((child.get("message") or "") or (child.text or ""))[:_MAX_MESSAGE] or None
                elif child.tag == "skipped":
                    status = "skipped"
                    message = (child.get("message") or "")[:_MAX_MESSAGE] or None
            cases.append({
                "class_name": tc.get("classname") or "",
                "name": tc.get("name") or "",
                "status": status,
                "time_s": float(tc.get("time") or 0),
                "message": message,
            })
            if len(cases) >= _MAX_CASES:
                return cases
    return cases
