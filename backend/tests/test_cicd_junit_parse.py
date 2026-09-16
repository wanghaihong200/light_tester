"""计划 16 Task 5:pytest junitxml 与 surefire 两种形态的统一解析。"""
from app.cicd.junit_parse import parse_junit_xml

PYTEST_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="0" failures="1" skipped="1" tests="3" time="1.5">
  <testcase classname="tests.test_login" name="test_ok" time="0.2"/>
  <testcase classname="tests.test_login" name="test_bad" time="0.3">
    <failure message="assert 1 == 2">(op_list...)</failure>
  </testcase>
  <testcase classname="tests.test_login" name="test_skip" time="0"><skipped message="xfail"/></testcase>
</testsuite></testsuites>"""

SUREFIRE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite xmlns="https://maven.apache.org/surefire" name="com.x.AuthApiTest" time="0.5">
  <testcase name="loginOk" classname="com.x.AuthApiTest" time="0.1"/>
  <testcase name="loginBad" classname="com.x.AuthApiTest" time="0.2">
    <error message="404" type="java.lang.AssertionError">stack...</error>
  </testcase>
</testsuite>"""


def test_parse_pytest_suite():
    cases = parse_junit_xml(PYTEST_XML)
    assert [c["name"] for c in cases] == ["test_ok", "test_bad", "test_skip"]
    assert [c["status"] for c in cases] == ["passed", "failed", "skipped"]
    assert cases[1]["message"] == "assert 1 == 2"
    assert cases[0]["time_s"] == 0.2


def test_parse_surefire_error_is_failed():
    cases = parse_junit_xml(SUREFIRE_XML)
    assert cases[0]["class_name"] == "com.x.AuthApiTest"
    assert cases[1]["status"] == "failed" and cases[1]["message"] == "404"


def test_message_truncated_and_cap_500():
    big = '<testsuite name="s">' + "".join(
        f'<testcase name="t{i}" classname="c"><failure message="{"x" * 5000}"/></testcase>'
        for i in range(600)) + "</testsuite>"
    cases = parse_junit_xml(big)
    assert len(cases) == 500
    assert len(cases[0]["message"]) == 2000


def test_garbage_xml_raises():
    import pytest
    import xml.etree.ElementTree as ET
    with pytest.raises(ET.ParseError):
        parse_junit_xml("<not-xml")
