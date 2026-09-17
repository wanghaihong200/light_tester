"""计划 17 Task 2:web 仓 pytest 用例函数扫描(ast.walk;ADR-0013 决策 2/3)。"""
from pathlib import Path

from app.cicd.ui_scan import scan_workspace

FUNC_FILE = '''import pytest

@pytest.mark.account("standard")
def test_01_login_state(page):
    """链路 1:配置加载 + 登录态缓存。
    首跑触发钩子登录并写 .auth 缓存。"""
    page.goto("/")

def test_02_pom_flow(page):
    pass

def helper():
    pass

class TestNotScanned:
    def test_inside_class(self):
        pass
'''

FILE_MARK = '''import pytest

pytestmark = pytest.mark.account("performance")

def test_file_bound(page):
    """整文件 marker 生效。"""
'''

LIST_MARK = '''import pytest

pytestmark = [pytest.mark.a, pytest.mark.b]

def test_two_file_marks():
    pass
'''

NO_DOC = '''def test_no_docstring(page):
    pass
'''


def _mk(ws: Path, rel: str, code: str) -> None:
    f = ws / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(code, encoding="utf-8")


def test_scan_functional_cases(tmp_path):
    _mk(tmp_path, "tests/test_smoke.py", FUNC_FILE)
    _mk(tmp_path, "pages/login_page.py", "def test_not_a_test_file():\n    pass\n")  # 非 test_*.py 不扫
    got = {(c["class_name"], c["method"]): c for c in scan_workspace(tmp_path)}
    assert list(got) == [("tests/test_smoke.py", "test_01_login_state"),
                         ("tests/test_smoke.py", "test_02_pom_flow")]  # helper 与类内方法不入册
    row = got[("tests/test_smoke.py", "test_01_login_state")]
    assert row["file_path"] == "tests/test_smoke.py" and row["framework"] == "pytest"
    assert row["title"] == "链路 1:配置加载 + 登录态缓存。"
    assert row["markers"] == ["account:standard"]
    assert got[("tests/test_smoke.py", "test_02_pom_flow")]["markers"] == []  # 不继承文件级(本文件无)


def test_title_fallback_none_without_docstring(tmp_path):
    _mk(tmp_path, "tests/test_x.py", NO_DOC)
    (row,) = scan_workspace(tmp_path)
    assert row["title"] is None


def test_file_level_pytestmark_single_and_list(tmp_path):
    _mk(tmp_path, "tests/test_performance_account.py", FILE_MARK)
    _mk(tmp_path, "tests/test_list_mark.py", LIST_MARK)
    got = {(c["class_name"], c["method"]): c for c in scan_workspace(tmp_path)}
    assert got[("tests/test_performance_account.py", "test_file_bound")]["markers"] == ["account:performance"]
    assert got[("tests/test_list_mark.py", "test_two_file_marks")]["markers"] == ["a", "b"]


def test_skips_venv_hidden_and_unparsable(tmp_path):
    _mk(tmp_path, ".venv/lib/test_venv.py", "def test_in_venv():\n    pass\n")
    _mk(tmp_path, ".git/hooks/test_git.py", "def test_in_git():\n    pass\n")
    _mk(tmp_path, "__pycache__/test_cache.py", "def test_in_cache():\n    pass\n")
    _mk(tmp_path, "tests/sub/test_nested.py", "def test_nested():\n    pass\n")  # tests 子目录要扫到
    _mk(tmp_path, "tests/test_broken.py", "def test_broken(:\n")  # 语法坏文件跳过不抛
    got = [c["method"] for c in scan_workspace(tmp_path)]
    assert got == ["test_nested"]


def test_null_byte_file_skipped_not_crash(tmp_path):
    """终审修复波:含 \\x00 的文件 ast.parse 抛异常,扫描必须跳过不炸。

    py3.12+ 对 null byte 抛 SyntaxError,py3.11- 抛 ValueError——
    两个都要接住(防回归钉:本机 3.12 改前已不炸,fix 护住旧解释器)。
    """
    _mk(tmp_path, "tests/test_good.py", "def test_good():\n    pass\n")
    bad = tmp_path / "tests" / "test_null.py"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"def test_x():\n    pass\n\x00")
    got = [c["method"] for c in scan_workspace(tmp_path)]
    assert got == ["test_good"]  # 坏文件跳过,好文件照常入册


def test_duplicate_def_deduped(tmp_path):
    _mk(tmp_path, "tests/test_dup.py", "def test_same():\n    pass\n\ndef test_same():\n    pass\n")
    got = scan_workspace(tmp_path)
    assert len(got) == 1
