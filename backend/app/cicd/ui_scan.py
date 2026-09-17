"""web 自动化仓 pytest 用例函数扫描:ast.walk 解析模块顶层 test_* 函数(ADR-0013 决策 2/3)。

v1 只扫顶层 test_* 函数(demo 工程与导出生成物均为函数式,全仓无 Test 类);类内方法是已知扩展点。
递归扫全仓 test_*.py(导出物在仓根、demo 形态在 tests/,一网打尽),跳过依赖/缓存/隐藏目录;
语法坏文件跳过不阻断(缺文件重扫即 stale 兜底)。标题=docstring 首行、缺省 None;
markers=@pytest.mark.X 装饰器 + 文件级 pytestmark 合并去重,展示串 "name" 或 "name:位置参数"。
浏览器参数化后缀不进模型(一函数一用例,ADR-0013 决策 2)。
"""
import ast
from pathlib import Path

_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
              ".mypy_cache", ".ruff_cache", ".auth", "dist", "build"}


def _dotted(node: ast.expr) -> str | None:
    """Attribute/Name 链的 dotted 名,如 pytest.mark.account;解不出返回 None。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def _marker_str(dec: ast.expr) -> str | None:
    """装饰器/pytestmark 元素 → marker 展示串;非 pytest.mark.X 返回 None。"""
    name, args = None, []
    if isinstance(dec, ast.Call):
        name, args = _dotted(dec.func), dec.args
    else:
        name = _dotted(dec)
    if not name or not name.startswith("pytest.mark."):
        return None
    short = name[len("pytest.mark."):]
    if not args:
        return short
    vals = []
    for a in args:
        try:
            vals.append(ast.literal_eval(a))
        except Exception:
            vals.append(ast.unparse(a))
    return f"{short}:{','.join(str(v) for v in vals)}"


def _file_markers(tree: ast.Module) -> list[str]:
    """模块级 pytestmark 赋值(单值或列表),保持声明序。"""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            vals = node.value.elts if isinstance(node.value, (ast.List, ast.Tuple)) else [node.value]
            return [s for s in (_marker_str(v) for v in vals) if s]
    return []


def scan_workspace(ws: Path) -> list[dict]:
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for path in sorted(ws.rglob("test_*.py")):
        rel = path.relative_to(ws).as_posix()
        if any(p in _SKIP_DIRS or p.startswith(".") for p in path.relative_to(ws).parts[:-1]):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError):  # ValueError=null byte(py3.11-;3.12+ 改抛 SyntaxError)
            continue
        file_marks = _file_markers(tree)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            if (rel, node.name) in seen:
                continue
            seen.add((rel, node.name))
            marks = list(dict.fromkeys(
                file_marks + [s for s in (_marker_str(d) for d in node.decorator_list) if s]))
            doc = ast.get_docstring(node)
            title = doc.strip().splitlines()[0].strip() if doc and doc.strip() else None
            results.append({
                "class_name": rel,       # 注册表 class_name 槽位:web 侧容器=文件
                "method": node.name,     # 注册表 method 槽位:函数名
                "file_path": rel,
                "framework": "pytest",
                "title": title,
                "markers": marks,
            })
    return results
