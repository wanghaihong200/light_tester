"""计划 16 Task 6:Java 测试方法扫描(TestNG 主,JUnit4/5 兼容;正则级解析)。"""
from pathlib import Path

from app.cicd.api_scan import scan_workspace

TESTNG = '''package com.x;
import org.testng.annotations.Test;

public class AuthApiTest {
    @Test
    public void loginOk() { }

    @Test(priority = 2, description = "bad login")
    public void loginBad() { }

    public void helper() { }
}
'''

JUNIT5 = '''package com.y;
import org.junit.jupiter.api.Test;

public class UsersApiTest {
    @Test
    void listUsers() { }
}
'''

PLAIN = 'package com.z;\npublic class Base {\n    public void setup() { }\n}\n'


def _mk(ws: Path, rel: str, code: str) -> None:
    f = ws / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(code, encoding="utf-8")


def test_scan_mixed_frameworks(tmp_path):
    _mk(tmp_path, "src/test/java/com/x/AuthApiTest.java", TESTNG)
    _mk(tmp_path, "src/test/java/com/y/UsersApiTest.java", JUNIT5)
    _mk(tmp_path, "src/main/java/com/x/Main.java", PLAIN)  # src/main 不扫
    got: dict[str, list[str]] = {}
    for c in scan_workspace(tmp_path):
        got.setdefault(c["class_name"], []).append(c["method"])
    assert got.get("com.x.AuthApiTest") == ["loginOk", "loginBad"]
    assert got.get("com.y.UsersApiTest") == ["listUsers"]
    tg_file = next(c["file_path"] for c in scan_workspace(tmp_path)
                   if c["class_name"] == "com.x.AuthApiTest")
    assert tg_file == "src/test/java/com/x/AuthApiTest.java"


def test_scan_reports_framework(tmp_path):
    _mk(tmp_path, "src/test/java/com/x/AuthApiTest.java", TESTNG)
    _mk(tmp_path, "src/test/java/com/y/UsersApiTest.java", JUNIT5)
    cases = scan_workspace(tmp_path)
    assert {c["class_name"]: c["framework"] for c in cases} == {
        "com.x.AuthApiTest": "testng", "com.y.UsersApiTest": "junit5"}


def test_scan_ignores_missing_parts(tmp_path):
    _mk(tmp_path, "src/test/java/Weird.java", "public class Weird { }\n")  # 无 package
    _mk(tmp_path, "src/test/java/com/q/Q.java", PLAIN)                     # 无 @Test
    assert scan_workspace(tmp_path) == []
