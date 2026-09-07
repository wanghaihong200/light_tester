from pathlib import Path

from app.app_automation.inspect_check import evaluate_checks, validate_checks
from app.app_automation.perf_csv import read_perf_csvs

# 模拟 inspect 的 page 树(字段名来自研究第 3 节:exportToJsonObject)
TREE = {
    "depth": 0, "className": "android.widget.FrameLayout", "nodeBound": [0, 0, 1080, 2400],
    "text": "", "description": "", "resourceId": "", "id": "", "packageName": "com.example.app",
    "visible": True, "type": "AbstractNodeTree",
    "children": [
        {"depth": 1, "className": "android.widget.TextView", "nodeBound": [0, 100, 1080, 160],
         "text": "欢迎回来", "description": "", "resourceId": "com.example.app:id/title",
         "id": "title", "packageName": "com.example.app", "visible": True, "type": "TextView", "children": []},
        {"depth": 1, "className": "android.widget.Button", "nodeBound": [0, 300, 540, 400],
         "text": "登录", "description": "login-btn", "resourceId": "com.example.app:id/btn_ok",
         "id": "btn_ok", "packageName": "com.example.app", "visible": True, "type": "Button", "children": []},
    ],
}


# ---- 检查点定义校验 ----
def test_validate_checks():
    assert validate_checks([]) == []
    assert validate_checks([{"type": "element_exists", "text": "登录"}]) == []
    errs = validate_checks([{"type": "element_exists"}])
    assert any("至少" in e for e in errs)
    errs2 = validate_checks([{"type": "text_contains"}])
    assert any("value" in e for e in errs2)
    errs3 = validate_checks([{"type": "hack"}, "not-dict"])
    assert len(errs3) == 2


# ---- 检查点评估 ----
def test_evaluate_text_contains():
    rs = evaluate_checks(TREE, [{"type": "text_contains", "value": "欢迎"}])
    assert rs == [{"type": "text_contains", "passed": True, "detail": rs[0]["detail"]}]
    assert "欢迎" in rs[0]["detail"]
    miss = evaluate_checks(TREE, [{"type": "text_contains", "value": "不存在"}])[0]
    assert miss["passed"] is False


def test_evaluate_element_exists_variants():
    # 全名 resource_id
    r1 = evaluate_checks(TREE, [{"type": "element_exists", "resource_id": "com.example.app:id/btn_ok"}])[0]
    assert r1["passed"] is True
    # 短名 resource_id(后缀匹配)
    r2 = evaluate_checks(TREE, [{"type": "element_exists", "resource_id": "btn_ok"}])[0]
    assert r2["passed"] is True
    # text + resource_id AND 语义:text 不匹配 → 失败
    r3 = evaluate_checks(TREE, [{"type": "element_exists", "text": "登录", "resource_id": "title"}])[0]
    assert r3["passed"] is False
    # description 命中
    r4 = evaluate_checks(TREE, [{"type": "element_exists", "description": "login-btn"}])[0]
    assert r4["passed"] is True


def test_evaluate_empty_tree_no_crash():
    rs = evaluate_checks({}, [{"type": "text_contains", "value": "x"}])
    assert rs[0]["passed"] is False


# ---- perf CSV 解析 ----
def test_read_perf_csvs_gbk_and_shape(tmp_path: Path):
    (tmp_path / "CPU.csv").write_bytes("时间,CPU(%)\n10:00:01,12.5\n10:00:02,18.0\n".encode("gbk"))
    (tmp_path / "FPS.csv").write_bytes("时间,FPS\n10:00:01,60\n".encode("utf-8-sig"))
    series = read_perf_csvs(tmp_path)
    assert [s["item"] for s in series] == ["CPU", "FPS"]  # 文件名排序
    cpu = series[0]
    assert cpu["columns"] == ["时间", "CPU(%)"]
    assert cpu["rows"] == [["10:00:01", "12.5"], ["10:00:02", "18.0"]]


def test_read_perf_csvs_empty_and_missing(tmp_path: Path):
    assert read_perf_csvs(tmp_path / "nope") == []
    (tmp_path / "bad.csv").write_bytes("only-header\n".encode("utf-8"))
    assert read_perf_csvs(tmp_path) == []  # 只有表头(行数<2)跳过
