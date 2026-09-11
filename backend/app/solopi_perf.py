"""性能测试域服务(计划 14 / ADR-0010):run 引用行登记、记录目录解析、导入落盘。
数据事实源是文件系统 CSV;本模块只管"记录从哪来、目录在哪",解析复用 perf_csv。"""
from pathlib import Path

from app.app_automation import perf_csv
from app.config import settings
from app.database import SessionLocal
from app.models import AppRun, PerfRecord


def run_perf_dir(app_run_id: int) -> Path:
    return Path(settings.app_data_dir) / "runs" / str(app_run_id) / "perf"


def record_perf_dir(record_id: int) -> Path:
    return Path(settings.app_data_dir) / "perf_records" / str(record_id)


def has_valid_perf_csv(dir_path: Path) -> bool:
    """有效=至少一个 CSV 带 ≥2 行数据(read_perf_csvs 自带该过滤)。"""
    return bool(perf_csv.read_perf_csvs(dir_path))


def record_data_dir(record: PerfRecord) -> Path:
    """统一数据目录:run 来源读执行目录(不复制数据),import 读自己的落盘目录。"""
    if record.source == "run":
        return run_perf_dir(record.app_run_id)  # type: ignore[arg-type]
    return record_perf_dir(record.id)


def register_run_perf_record(run_id: int) -> None:
    """执行终态(passed/failed)且有有效 perf CSV → 幂等登记引用行;cancelled/空数据跳过。
    自开 Session(对齐 executor._persist 模式),执行线程/请求线程均可安全调用。"""
    with SessionLocal() as db:
        run = db.get(AppRun, run_id)
        if run is None or run.status not in ("passed", "failed"):
            return
        if not has_valid_perf_csv(run_perf_dir(run_id)):
            return
        exists = db.query(PerfRecord).filter_by(source="run", app_run_id=run_id).first()
        if exists:
            return
        db.add(PerfRecord(
            project_id=run.project_id, source="run",
            name=f"{run.script_name}@{run.device_serial}",
            app_run_id=run.id, script_id=run.script_id, script_name=run.script_name,
            device_serial=run.device_serial, perf_items=run.perf_items or [],
            data_complete=True, perf_summary=run.perf_summary,
            started_at=run.started_at, finished_at=run.finished_at,
        ))
        db.commit()


def save_imported_csvs(record_id: int, files: list[dict]) -> int:
    """把 perf-history-get 的 files[].preview 逐文件写进 import 落盘目录(utf-8;
    read_perf_csvs 读侧 utf-8-sig→gbk 兼容)。preview 为空/缺省的文件跳过,返回落盘数。
    真机 preview 是 dict({charset, fileName, modifiedAt, pathAvailable, relativePath,
    sizeBytes, text, truncated}),CSV 文本在 text 键(2026-09-10 冒烟:当字符串
    write_text 报 "data must be str, not dict");字符串 preview(旧桩)兼容。
    文件级 preview.truncated 不影响落盘(截断感知在 router,置 data_complete=False)。"""
    out_dir = record_perf_dir(record_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in files or []:
        if not isinstance(f, dict):  # Task5 顺手硬化:CLI 载荷异常项直接跳过(防 AttributeError)
            continue
        preview = f.get("preview")
        text = preview.get("text") if isinstance(preview, dict) else preview
        name = str(f.get("fileName") or "").replace("/", "_").replace("\\", "_")
        if not text or not name:
            continue
        if name in ("", ".", ".."):  # Task5 顺手硬化:归一后仍可能剩路径穿越名,拒落盘
            continue
        (out_dir / name).write_text(text, encoding="utf-8")
        n += 1
    return n
