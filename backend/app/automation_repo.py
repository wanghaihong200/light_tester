# app/automation_repo.py
"""自动化仓(kind api/web/app)的解析与 upsert。仓配置缺失时给 400 而非 500。"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import AutomationRepo

KINDS = ("api", "web", "app")


def resolve_repo(db: Session, project_id: int, kind: str) -> AutomationRepo | None:
    if kind not in KINDS:
        raise HTTPException(400, f"未知仓分类: {kind}(必须是 {'/'.join(KINDS)})")
    return (
        db.query(AutomationRepo)
        .filter_by(project_id=project_id, kind=kind, is_deleted=False)
        .first()
    )


def require_repo(db: Session, project_id: int, kind: str) -> AutomationRepo:
    repo = resolve_repo(db, project_id, kind)
    if repo is None:
        raise HTTPException(400, f"项目未配置 {kind} 自动化仓,请先在自动化工程页配置")
    return repo
