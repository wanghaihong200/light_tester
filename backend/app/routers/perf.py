# app/routers/perf.py
"""性能测试域 API(计划 14 / ADR-0010):性能记录 CRUD + 统一 series。
数据消费统一走 record_data_dir → read_perf_csvs;run 来源不复制数据(读执行目录)。"""
import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import solopi_perf  # 顶层模块(brief 稿误写 app.app_automation.solopi_perf)
from app.app_automation import perf_csv
from app.auth import get_current_user
from app.database import get_db
from app.models import PerfRecord, User
from app.permissions import ensure_project_access
from app.schemas import PerfRecordOut

router = APIRouter(prefix="/api", tags=["perf"])


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
        cols = ((r.perf_summary or {}).get("columns")) or []
        g["points"].append({
            "record_id": r.id, "finished_at": r.finished_at.isoformat(),
            "series": {str(c.get("index")): {"mean": c.get("mean"), "p90": c.get("p90")}
                       for c in cols if c.get("index") is not None},
        })
    return {"groups": list(groups.values())}
