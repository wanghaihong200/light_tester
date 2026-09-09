# app/routers/perf.py
"""性能测试域 API(计划 14 / ADR-0010):性能记录 CRUD + 统一 series。
数据消费统一走 record_data_dir → read_perf_csvs;run 来源不复制数据(读执行目录)。"""
import shutil

from fastapi import APIRouter, Depends, HTTPException
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
