# app/routers/repo.py
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.git_service import (
    ChangeFile, FileNode, GitError, NothingToCommit, PushConflict,
    PushResult, SyncResult, git_status, list_files,
    list_remote_branches, push_files, read_file, sync_repo,
    working_copy_path,
)
from app.models import Project

router = APIRouter(prefix="/api/projects/{project_id}/repo", tags=["repo"], dependencies=[Depends(get_current_user)])

_LANG_MAP = {".java": "java", ".xml": "xml", ".properties": "properties", ".md": "markdown"}


def _get_project(project_id: int, db: Session) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    return p


# Issue G: 移除 validate_repo_url 调用 —— validate_repo_url 严格只允许 http(s),
# 会拒绝 file:// 协议导致本地 bare 仓测试失败。生产 API 入口 create_job
# (Task 6)已强制 http(s);此处 sync_repo→ensure_repo→build_remote_url 内部
# 已分流 file://(原样)/http(s)(注入 token)/其他(抛 GitError stage=url)。
class SyncRequest(BaseModel):
    branch: str | None = None  # 指定则切换到该远程分支再同步


@router.post("/sync", response_model=SyncResult)
def repo_sync(project_id: int, payload: SyncRequest | None = None, db: Session = Depends(get_db)):
    p = _get_project(project_id, db)
    try:
        branch = payload.branch if payload else None
        return sync_repo(p, branch)
    except GitError as e:
        if e.stage == "url":
            raise HTTPException(400, e.message)
        raise HTTPException(409, {"stage": e.stage, "error": e.message})


@router.get("/files")
def repo_files(project_id: int, db: Session = Depends(get_db)):
    p = _get_project(project_id, db)
    wc = working_copy_path(p)
    if not (wc.exists() and (wc / ".git").exists()):
        return {"needs_sync": True}
    try:
        return list_files(p)
    except GitError as e:
        raise HTTPException(409, e.message)


@router.get("/file")
def repo_file(project_id: int, path: str = Query(...), db: Session = Depends(get_db)):
    p = _get_project(project_id, db)
    try:
        content = read_file(p, path)
    except GitError as e:
        if e.stage == "path" and "不存在" in e.message:
            raise HTTPException(404, e.message)
        raise HTTPException(400, e.message)
    lang = _LANG_MAP.get(Path(path).suffix, "plaintext")
    return {"path": path, "content": content, "language": lang}


@router.get("/changes")
def repo_changes(project_id: int, db: Session = Depends(get_db)):
    p = _get_project(project_id, db)
    try:
        return {"files": [c.model_dump() for c in git_status(p)]}
    except GitError as e:
        raise HTTPException(409, e.message)


@router.get("/branches")
def repo_branches(project_id: int, db: Session = Depends(get_db)):
    p = _get_project(project_id, db)
    try:
        return {"branches": list_remote_branches(p)}
    except GitError as e:
        raise HTTPException(409, e.message)


class PushRequest(BaseModel):
    files: list[str]
    branch: str
    commit_message: str | None = None


@router.post("/push", response_model=PushResult)
def repo_push(project_id: int, payload: PushRequest, db: Session = Depends(get_db)):
    p = _get_project(project_id, db)
    msg = payload.commit_message or f"AI 生成接口测试 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    try:
        return push_files(p, payload.files, payload.branch, msg)
    except NothingToCommit as e:
        raise HTTPException(400, {"stage": e.stage, "error": e.message})
    except PushConflict as e:
        raise HTTPException(409, {"stage": e.stage, "error": e.message})
    except GitError as e:
        raise HTTPException(409, {"stage": e.stage, "error": e.message})
