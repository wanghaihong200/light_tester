# app/routers/perf.py
"""性能测试域 API(计划 14 / ADR-0010):性能记录 CRUD + 统一 series。
数据消费统一走 record_data_dir → read_perf_csvs;run 来源不复制数据(读执行目录)。"""
import shutil
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import solopi_perf  # 顶层模块(brief 稿误写 app.app_automation.solopi_perf)
from app.app_automation import perf_csv, solopi_cli
from app.app_automation.solopi_cli import CliError
from app.auth import get_current_user
from app.database import get_db
from app.models import PerfRecord, User
from app.permissions import ensure_project_access
from app.schemas import PerfRecordOut

router = APIRouter(prefix="/api", tags=["perf"])


def _file_key(stem: str) -> str:
    """文件 stem → 稳定大类 key(采集项段)。SoloPi 拆文件名模式
    <指标名>_<采集项>_<hex16>_<ts>_<ts>.csv,取第二段(如 Temperature/CPU/Network);
    段数<2 退第一段;空段用全 stem。与前端 perfOption.ts 的 fileKeyOf 同算法
    (两端注释互指,改动必须同步):趋势聚合键跨 run 稳定正是趋势的意义。"""
    parts = stem.split("_")
    key = parts[1] if len(parts) > 1 else parts[0]
    return key or stem


def _trend_series(summary: dict | None) -> dict[str, dict]:
    """perf_summary → {趋势键: {mean, p90}}(null 安全)。
    CLI perf-analyze 真实结构={files:[{path, columns:[{name, kind, mean, p90, …}]}]},
    遍历 files,每 kind=numeric 列产出键=<fileKeyOf(stem)>::<列名>(计划14 冒烟修复;
    此前按顶层 {columns:[…]} 解析 → 趋势恒空)。"""
    out: dict[str, dict] = {}
    for f in (summary or {}).get("files") or []:
        stem = Path(str(f.get("path") or "")).stem
        for c in f.get("columns") or []:
            if c.get("kind") != "numeric" or not c.get("name"):
                continue
            out[f"{_file_key(stem)}::{c['name']}"] = {"mean": c.get("mean"), "p90": c.get("p90")}
    return out


def _get_record(db: Session, record_id: int, current: User, min_role: str) -> PerfRecord:
    rec = db.get(PerfRecord, record_id)
    if rec is None:
        raise HTTPException(404, "perf record not found")
    ensure_project_access(db, current, rec.project_id, min_role)
    return rec


@router.get("/projects/{project_id}/perf-records", response_model=list[PerfRecordOut])
def list_records(project_id: int, source: str | None = None, script_id: int | None = None,
                 device_serial: str | None = None,
                 db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    q = db.query(PerfRecord).filter(PerfRecord.project_id == project_id)
    if source:
        q = q.filter(PerfRecord.source == source)
    if script_id is not None:
        q = q.filter(PerfRecord.script_id == script_id)
    if device_serial:
        q = q.filter(PerfRecord.device_serial == device_serial)
    return q.order_by(PerfRecord.id.desc()).limit(100).all()


@router.get("/perf-records/{record_id}", response_model=PerfRecordOut)
def get_record(record_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return _get_record(db, record_id, current, "viewer")


@router.delete("/perf-records/{record_id}")
def delete_record(record_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rec = _get_record(db, record_id, current, "editor")
    if rec.source == "import":  # import 删除连数据目录;run 只删引用行(ADR-0010)
        shutil.rmtree(solopi_perf.record_perf_dir(rec.id), ignore_errors=True)
    db.delete(rec)
    db.commit()
    return {"ok": True}


@router.get("/perf-records/{record_id}/series")
def record_series(record_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    rec = _get_record(db, record_id, current, "viewer")
    return {"record": PerfRecordOut.model_validate(rec).model_dump(mode="json"),
            "series": perf_csv.read_perf_csvs(solopi_perf.record_data_dir(rec))}


class CompareBody(BaseModel):
    record_ids: list[int]


@router.post("/projects/{project_id}/perf-records/compare")
def compare_records(project_id: int, body: CompareBody, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    ensure_project_access(db, current, project_id, "viewer")
    if not (2 <= len(body.record_ids) <= 10):
        raise HTTPException(400, "对比需勾选 2~10 条记录")
    recs = (db.query(PerfRecord)
            .filter(PerfRecord.project_id == project_id, PerfRecord.id.in_(body.record_ids))
            .order_by(PerfRecord.id.desc()).all())
    if len(recs) != len(body.record_ids):
        raise HTTPException(404, "存在不属于本项目或已删除的记录")
    series = {str(r.id): perf_csv.read_perf_csvs(solopi_perf.record_data_dir(r)) for r in recs}
    return {"records": [PerfRecordOut.model_validate(r).model_dump(mode="json") for r in recs],
            "series": series}


@router.get("/projects/{project_id}/perf-trend")
def perf_trend(project_id: int, script_id: int | None = None, device_serial: str | None = None,
               db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """趋势:仅 run 来源(脚本口径);分组键=script_id+device_serial;数据取 perf_summary(不碰 CSV)。"""
    ensure_project_access(db, current, project_id, "viewer")
    q = (db.query(PerfRecord)
         .filter(PerfRecord.project_id == project_id, PerfRecord.source == "run",
                 PerfRecord.script_id.isnot(None), PerfRecord.finished_at.isnot(None)))
    if script_id is not None:
        q = q.filter(PerfRecord.script_id == script_id)
    if device_serial:
        q = q.filter(PerfRecord.device_serial == device_serial)
    recs = q.order_by(PerfRecord.finished_at.asc()).all()
    groups: dict[tuple, dict] = {}
    for r in recs:
        key = (r.script_id, r.device_serial)
        g = groups.setdefault(key, {"script_id": r.script_id, "script_name": r.script_name,
                                    "device_serial": r.device_serial, "points": []})
        g["points"].append({
            "record_id": r.id, "finished_at": r.finished_at.isoformat(),
            "series": _trend_series(r.perf_summary),
        })
    return {"groups": list(groups.values())}


# ---- 计划 14 Task 5:设备历史发现 + 手动导入 ----

class ImportBody(BaseModel):
    serial: str
    history_id: str
    name: str | None = None


def _ms_to_dt(ms) -> datetime | None:
    # naive 本地时间,对齐 executor 的 datetime.now() 惯例( DateTime 列不存时区;
    # 带 UTC 落库会与平台其余时间整体错 8 小时,前端直显即错位——计划14 终审修复)
    try:
        return datetime.fromtimestamp(int(ms) / 1000) if ms else None
    except (TypeError, ValueError):
        return None


@router.get("/app-devices/{serial}/perf-history")
def device_perf_history(serial: str, limit: int = Query(50, ge=1, le=500),
                        db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    """设备端 SoloPi 性能历史列表;已导入的条目回填平台记录 id(前端防重复导入)。
    授权:登录即可读——对齐 app_scripts.py 的 GET /app-devices/{serial}/perf-items
    (app_device_perf_items)既有口径(设备无项目归属,不挂项目闸;brief 稿假设
    editor,与仓库 /app-devices 系惯例不符,以仓库惯例为准)。"""
    try:
        payload = solopi_cli.perf_history_list(serial, limit=limit)
    except CliError as e:
        raise HTTPException(400, f"拉取设备历史失败: {e.message}")
    imported = {r.source_ref: r.id for r in db.query(PerfRecord).filter(
        PerfRecord.source == "import", PerfRecord.source_ref.isnot(None)).all()}
    items = []
    # CLI perf-history-list 真实返回顶层 records(计划14 冒烟修复;此前取 items → 永远空),
    # items 兜底兼容旧桩/旧 CLI。
    for it in payload.get("records") or payload.get("items") or []:
        items.append({"id": it.get("id"), "start_time": it.get("startTime"),
                      "end_time": it.get("endTime"), "file_count": it.get("fileCount"),
                      "size_bytes": it.get("sizeBytes"), "metrics": it.get("metrics") or [],
                      "imported_record_id": imported.get(str(it.get("id")))})
    return {"items": items}


@router.post("/projects/{project_id}/perf-records/import", response_model=PerfRecordOut, status_code=201)
def import_history(project_id: int, body: ImportBody, db: Session = Depends(get_db),
                   current: User = Depends(get_current_user)):
    """把设备端一条历史导入为 import 来源记录:CLI 详情→preview 落盘→perf-analyze 统计。
    重复导入(同 source_ref)→409;CLI 失败→400;截断(filesTruncated)→data_complete=False。"""
    ensure_project_access(db, current, project_id, "editor")
    dup = db.query(PerfRecord).filter(PerfRecord.source == "import",
                                      PerfRecord.source_ref == body.history_id).first()
    if dup:
        raise HTTPException(409, f"该设备历史已导入(perf 记录 #{dup.id})")
    try:
        detail = solopi_cli.perf_history_get(body.serial, body.history_id)
    except CliError as e:
        raise HTTPException(400, f"拉取历史详情失败: {e.message}")
    files = detail.get("files") or []
    rec = PerfRecord(project_id=project_id, source="import",
                     name=body.name or f"设备导入 {body.history_id[:20]}",
                     device_serial=body.serial, perf_items=detail.get("metrics") or [],
                     source_ref=body.history_id,
                     data_complete=not bool(detail.get("filesTruncated")),
                     started_at=_ms_to_dt(detail.get("startTime")),
                     finished_at=_ms_to_dt(detail.get("endTime")))
    db.add(rec)
    db.commit()
    db.refresh(rec)
    try:
        saved = solopi_perf.save_imported_csvs(rec.id, files)
        if saved == 0:  # 无可落盘内容:回滚删除刚建的行,不留空壳记录
            db.delete(rec)
            db.commit()
            raise HTTPException(400, "历史详情未含可落盘的 CSV 内容(preview 为空)")
        try:
            rec.perf_summary = solopi_cli.perf_analyze(str(solopi_perf.record_perf_dir(rec.id)))
        except CliError as e:
            rec.perf_summary = {"error": f"统计分析失败: {e.message}"}
        db.commit()
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        # 计划14 终审:落盘段任何异常同样回滚(删行+清半落盘目录),不留空壳记录
        db.rollback()  # 先复位会话(异常可能来自 commit/脏赋值),rec 此前已提交仍是持久态
        shutil.rmtree(solopi_perf.record_perf_dir(rec.id), ignore_errors=True)
        db.delete(rec)
        db.commit()
        raise HTTPException(400, f"导入落盘失败: {e}") from e
    return rec
