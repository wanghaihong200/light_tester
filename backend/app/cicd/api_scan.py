"""api 自动化仓 Java 测试方法扫描:TestNG(org.testng.@Test)为主,JUnit4/5 兼容。

正则级解析(不引入 Java AST 依赖):package + class 得全限定名,`@Test` 行向下 lookahead
数行找 `void 方法名(`;栈是仓文件规模(个位数~两位数文件),精度足够,注册表唯一约束兜底去重。
"""
import re
from pathlib import Path

_PKG_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
_CLASS_RE = re.compile(r"^\s*(?:public\s+)?(?:final\s+|abstract\s+)*class\s+(\w+)", re.M)
_TEST_RE = re.compile(r"@Test\b")
_METHOD_RE = re.compile(r"^\s*(?:public\s+)?void\s+(\w+)\s*\(")
_LOOKAHEAD = 6  # @Test(...) 注解参数换行时方法声明在其后数行内

_FRAMEWORKS = {
    "org.testng.annotations": "testng",
    "org.junit.jupiter.api": "junit5",
    "org.junit": "junit4",
}


def scan_workspace(ws: Path) -> list[dict]:
    root = ws / "src" / "test" / "java"
    if not root.is_dir():
        return []
    results: list[dict] = []
    for java in sorted(root.rglob("*.java")):
        text = java.read_text(encoding="utf-8", errors="replace")
        pkg = _PKG_RE.search(text)
        cls = _CLASS_RE.search(text)
        if not pkg or not cls:
            continue
        framework = "testng"
        for imp, fw in _FRAMEWORKS.items():
            if re.search(rf"import\s+{re.escape(imp)}(?:\.\w+)?\.Test\s*;", text):
                framework = fw
                break
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not _TEST_RE.search(line):
                continue
            for j in range(i, min(i + _LOOKAHEAD, len(lines))):
                m = _METHOD_RE.match(lines[j])
                if m:
                    results.append({
                        "class_name": f"{pkg.group(1)}.{cls.group(1)}",
                        "method": m.group(1),
                        "file_path": java.relative_to(ws).as_posix(),
                        "framework": framework,
                    })
                    break
    return results
