# app/automation_repo.py
"""自动化仓(kind api/web/app)的解析与 upsert。仓配置缺失时给 400 而非 500。"""
from urllib.parse import urlparse

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


def upsert_repo(
    db: Session, project_id: int, kind: str, repo_url: str | None, repo_token: str | None, user_id: int | None
) -> AutomationRepo:
    if kind not in KINDS:
        raise HTTPException(400, f"未知仓分类: {kind}(必须是 {'/'.join(KINDS)})")
    repo = resolve_repo(db, project_id, kind)
    if repo is None:
        repo = AutomationRepo(project_id=project_id, kind=kind, repo_url="", repo_token=None)
        db.add(repo)
    repo.repo_url = (repo_url or "").strip()
    repo.repo_token = (repo_token or "").strip() or None
    repo.updated_by = user_id
    db.commit()
    db.refresh(repo)
    return repo


def validate_repo_url_loose(url: str) -> None:
    """仓配置 URL 校验:允许 http(s)(生产)与 file://(测试/本地),其余拒绝。"""
    p = urlparse(url or "")
    if p.scheme not in ("http", "https", "file") or (p.scheme in ("http", "https") and not p.netloc):
        raise HTTPException(400, "repo_url 必须是 http(s) 或 file 且 host 非空")
