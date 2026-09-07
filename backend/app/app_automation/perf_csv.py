"""perf 连续采集 CSV 解析(纯函数)。设备默认 GBK 编码(研究第 3 节),utf-8-sig → gbk 依次尝试。"""
import csv
import io
from pathlib import Path


def read_perf_csvs(dir_path: Path) -> list[dict]:
    """目录下每个 *.csv 一个序列 {item, columns, rows};item 取文件名 stem;目录不存在返回 []。"""
    out: list[dict] = []
    if not dir_path.exists():
        return out
    for p in sorted(dir_path.glob("*.csv")):
        raw = p.read_bytes()
        text = None
        for enc in ("utf-8-sig", "gbk"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw.decode("utf-8", "replace")
        rows = [r for r in csv.reader(io.StringIO(text)) if any(str(c).strip() for c in r)]
        if len(rows) < 2:
            continue  # 只有表头(或空文件)跳过
        out.append({"item": p.stem, "columns": rows[0], "rows": rows[1:]})
    return out
