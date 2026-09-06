# app/routers/repo.py
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.automation_repo import (
    KINDS, require_repo, resolve_repo, upsert_repo, validate_repo_url_loose,
)
from app.auth import get_current_user
from app.database import get_db
from app.git_service import (
    ChangeFile, FileNode, GitError, NothingToCommit, PushConflict,
    PushResult, SyncResult, git_status, list_files,
    list_remote_branches, push_files, read_file, sync_repo,
    working_copy_path,
)
from app.models import AutomationRepo, Project, User
from app.permissions import ensure_project_access

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
# 计划 11 Task 2:全部端点加 ?kind=(默认 api),严格按 AutomationRepo 行解析,不回退 Project 旧列。
class SyncRequest(BaseModel):
    branch: str | None = None  # 指定则切换到该远程分支再同步


@router.post("/sync", response_model=SyncResult)
def repo_sync(project_id: int, payload: SyncRequest | None = None, kind: str = Query("api"), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = _get_project(project_id, db)
    # Task 7:sync 拉外部仓并改写工作副本,写外部系统 → editor+(viewer 403,非成员 404)
    ensure_project_access(db, current, p.id, "editor")
    repo = require_repo(db, project_id, kind)
    try:
        branch = payload.branch if payload else None
        return sync_repo(repo, branch)
    except GitError as e:
        if e.stage == "url":
            raise HTTPException(400, e.message)
        raise HTTPException(409, {"stage": e.stage, "error": e.message})


@router.get("/files")
def repo_files(project_id: int, kind: str = Query("api"), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = _get_project(project_id, db)
    # Task 7:文件浏览是读端点,viewer 可读(非成员 404)
    ensure_project_access(db, current, p.id, "viewer")
    repo = resolve_repo(db, project_id, kind)
    if repo is None:
        return {"needs_config": True}
    wc = working_copy_path(repo)
    if not (wc.exists() and (wc / ".git").exists()):
        return {"needs_sync": True}
    try:
        return list_files(repo)
    except GitError as e:
        raise HTTPException(409, e.message)


@router.get("/file")
def repo_file(project_id: int, path: str = Query(...), kind: str = Query("api"), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = _get_project(project_id, db)
    ensure_project_access(db, current, p.id, "viewer")  # Task 7:读端点 viewer
    repo = require_repo(db, project_id, kind)
    try:
        content = read_file(repo, path)
    except GitError as e:
        if e.stage == "path" and "不存在" in e.message:
            raise HTTPException(404, e.message)
        raise HTTPException(400, e.message)
    lang = _LANG_MAP.get(Path(path).suffix, "plaintext")
    return {"path": path, "content": content, "language": lang}


@router.get("/changes")
def repo_changes(project_id: int, kind: str = Query("api"), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = _get_project(project_id, db)
    ensure_project_access(db, current, p.id, "viewer")  # Task 7:读端点 viewer
    repo = require_repo(db, project_id, kind)
    try:
        return {"files": [c.model_dump() for c in git_status(repo)]}
    except GitError as e:
        raise HTTPException(409, e.message)


@router.get("/branches")
def repo_branches(project_id: int, kind: str = Query("api"), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = _get_project(project_id, db)
    ensure_project_access(db, current, p.id, "viewer")  # Task 7:读端点 viewer
    repo = require_repo(db, project_id, kind)
    try:
        return {"branches": list_remote_branches(repo)}
    except GitError as e:
        raise HTTPException(409, e.message)


class PushRequest(BaseModel):
    files: list[str]
    branch: str
    commit_message: str | None = None


@router.post("/push", response_model=PushResult)
def repo_push(project_id: int, payload: PushRequest, kind: str = Query("api"), db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = _get_project(project_id, db)
    # Task 7:push 推外部仓,写外部系统 → editor+(闸在任何 git 动作之前)
    ensure_project_access(db, current, p.id, "editor")
    repo = require_repo(db, project_id, kind)
    msg = payload.commit_message or f"AI 生成接口测试 {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    try:
        return push_files(repo, payload.files, payload.branch, msg)
    except NothingToCommit as e:
        raise HTTPException(400, {"stage": e.stage, "error": e.message})
    except PushConflict as e:
        raise HTTPException(409, {"stage": e.stage, "error": e.message})
    except GitError as e:
        raise HTTPException(409, {"stage": e.stage, "error": e.message})


# ---- 计划 11 Task 2:多仓配置 API(挂在既有 router prefix 下,与 Task 8 前端路径一致) ----

@router.get("/automation-repos")
def list_automation_repos(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    p = _get_project(project_id, db)
    ensure_project_access(db, current, p.id, "viewer")
    rows = db.query(AutomationRepo).filter_by(project_id=project_id, is_deleted=False).all()
    return [
        {"id": r.id, "kind": r.kind, "repo_url": r.repo_url, "repo_token": r.repo_token, "updated_at": r.updated_at}
        for r in rows
    ]


class AutomationRepoSave(BaseModel):
    repo_url: str
    repo_token: str | None = None


@router.put("/automation-repos/{kind}")
def put_automation_repo(
    project_id: int, kind: str, payload: AutomationRepoSave,
    db: Session = Depends(get_db), current: User = Depends(get_current_user),
):
    p = _get_project(project_id, db)
    ensure_project_access(db, current, p.id, "editor")  # 与 update_project 同权
    validate_repo_url_loose(payload.repo_url)
    r = upsert_repo(db, project_id, kind, payload.repo_url, payload.repo_token, current.id)
    return {"id": r.id, "kind": r.kind, "repo_url": r.repo_url, "repo_token": r.repo_token}
