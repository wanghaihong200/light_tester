# UI自动化脚本 CRUD:录制产出的步骤 DSL 文档的增删改查(+ Web 端导出 Playwright 推送 web 仓)
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.automation_repo import require_repo
from app.auth import get_current_user
from app.database import get_db
from app.git_service import (
    GitError,
    NothingToCommit,
    PushConflict,
    push_files,
    sync_repo,
    working_copy_path,
)
from app.models import Project, UiAuthState, UiScript, User
from app.permissions import ensure_project_access
from app.schemas import UiScriptOut, UiScriptSave
from app.ui_automation.playwright_export import collect_export_bundle

router = APIRouter(prefix="/api", tags=["ui-scripts"], dependencies=[Depends(get_current_user)])

# 合法端列表:script.meta.target 只允许这三种,缺省/非法一律归为 web(v1 脚本必须 web)
_TARGETS = ("web", "android", "harmony")


def _derive_target(script: dict) -> str:
    # 服务端派生 driver_target,客户端不可直写;meta 缺失或 target 非法时兜底 web
    meta = script.get("meta") if isinstance(script, dict) else None
    t = (meta or {}).get("target") if isinstance(meta, dict) else None
    return t if t in _TARGETS else "web"


def _get_owned(db: Session, current: User, script_id: int, min_role: str) -> UiScript:
    # 软删后的行对外视为不存在,与列表口径一致;取行后按所属项目过角色闸门
    row = db.get(UiScript, script_id)
    if row is None or row.is_deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ui script not found")
    ensure_project_access(db, current, row.project_id, min_role)
    return row


@router.post("/projects/{project_id}/ui-scripts", response_model=UiScriptOut, status_code=status.HTTP_201_CREATED)
def create_script(project_id: int, payload: UiScriptSave, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    if db.get(Project, project_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    ensure_project_access(db, current, project_id, "editor")  # 建脚本 = 写
    row = UiScript(project_id=project_id, **payload.model_dump(), created_by=current.id)  # updated_by 仅 update 时写
    row.driver_target = _derive_target(payload.script)  # 端由脚本内容服务端派生落列
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/projects/{project_id}/ui-scripts", response_model=list[UiScriptOut])
def list_scripts(project_id: int, scope: str | None = None, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # scope 缺省=全部(老前端零影响);web_legacy=纯选择器 Web 脚本;cross=其余(跨端或含 AI 步)
    ensure_project_access(db, current, project_id, "viewer")
    rows = (
        db.query(UiScript)
        .filter(UiScript.project_id == project_id, UiScript.is_deleted.is_(False))
        .order_by(UiScript.id.desc())
        .all()
    )
    if scope is None:
        return rows
    if scope not in ("web_legacy", "cross"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "scope 必须是 web_legacy 或 cross")

    def has_ai(r: UiScript) -> bool:
        # 脚本含任一 ai_* 步即视为跨端脚本(需 Node 路径执行)
        return any(isinstance(st, dict) and str(st.get("action", "")).startswith("ai_")
                   for st in (r.script.get("steps") or []))

    if scope == "web_legacy":
        return [r for r in rows if r.driver_target == "web" and not has_ai(r)]
    return [r for r in rows if r.driver_target != "web" or has_ai(r)]


@router.get("/ui-scripts/{script_id}", response_model=UiScriptOut)
def get_script(script_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return _get_owned(db, current, script_id, "viewer")


@router.put("/ui-scripts/{script_id}", response_model=UiScriptOut)
def update_script(script_id: int, payload: UiScriptSave, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    row = _get_owned(db, current, script_id, "editor")
    for k, v in payload.model_dump().items():
        setattr(row, k, v)
    row.driver_target = _derive_target(payload.script)  # 更新时同样按新脚本内容重新派生
    row.updated_by = current.id
    db.commit()
    db.refresh(row)
    return row


@router.delete("/ui-scripts/{script_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_script(script_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    row = _get_owned(db, current, script_id, "editor")
    # 软删:ui_runs.script_id 外键历史必须不断链,禁止物理 delete
    row.is_deleted = True
    db.commit()


class UiScriptExportRequest(BaseModel):
    branch: str
    commit_message: str | None = None


@router.post("/ui-scripts/{script_id}/export")
def export_script(
    script_id: int,
    payload: UiScriptExportRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # 先可见性(非成员 404,不泄漏存在性),再过 editor 闸(推外部仓 = 写操作,viewer 403)
    s = _get_owned(db, current, script_id, "viewer")
    ensure_project_access(db, current, s.project_id, "editor")
    doc = s.script or {}
    target = _derive_target(doc)  # meta 缺失/非法兜底 web,与保存口径一致
    if target != "web":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"仅 driver_target=web 的脚本可导出 Playwright(当前 {target})")

    def lookup(ref: int) -> tuple[str, dict] | None:
        sub = db.query(UiScript).filter(UiScript.id == ref, UiScript.is_deleted.is_(False)).first()
        return (sub.name, sub.script) if sub else None

    bundle = collect_export_bundle(s.id, s.name, doc, lookup)

    # 登录态:meta.auth_state_id → 附带 storage_state 文件 + browser_context_args fixture 注入
    auth_state_id = (doc.get("meta") or {}).get("auth_state_id")
    if auth_state_id:
        auth = db.get(UiAuthState, auth_state_id)
        if auth is None or auth.is_deleted:
            bundle.errors.append(f"登录态 #{auth_state_id} 不存在或已删除,请先在脚本编辑中变更登录态")
        else:
            storage = Path(auth.storage_path)
            if not storage.exists():
                bundle.errors.append(f"登录态「{auth.name}」的 storage_state 文件缺失({auth.storage_path})")
            else:
                rel = f"auth_states/{auth.name}.json"
                bundle.files[rel] = storage.read_text(encoding="utf-8")
                ctx = (
                    "\n\n@pytest.fixture\n"
                    "def browser_context_args(browser_context_args):\n"
                    f'    return {{**browser_context_args, "storage_state": str(Path(__file__).parent / "{rel}")}}\n'
                )
                main_py = next(f for f in bundle.files if f.startswith("test_"))
                code = bundle.files[main_py]
                if "from pathlib import Path" not in code:
                    # 文件头已 import pytest,此处只补 Path(生成器头两行 import 保持不动)
                    code = code.replace(
                        "from playwright.sync_api import Page, expect",
                        "from pathlib import Path\n\nfrom playwright.sync_api import Page, expect", 1)
                bundle.files[main_py] = code + ctx
                # RUN.md 拼入登录态说明(占位符在生成期已 format,此处防残留并落说明)
                bundle.files["RUN.md"] = (
                    bundle.files["RUN.md"].replace("{auth_section}", "").replace("{auth_note}", "")
                    + f"\n本次导出附带登录态「{auth.name}」:文件 `{rel}`(browser_context_args 已注入 storage_state)。\n"
                )

    if bundle.errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"errors": bundle.errors})

    repo = require_repo(db, s.project_id, "web")
    try:
        sync_repo(repo)  # 同步失败不阻断(首推/离线可继续);wc 就绪后再落盘
    except GitError:
        pass
    # push_files 只 git add 给定路径,产物必须先写入 working copy(auth_states/ 需先建目录)。
    # 写盘前先做与 push_files 同款的路径包含检查:auth.name 未消毒,名字含 ../ 时
    # 不能等 push 阶段才拦(文件此时已落盘越界),必须在写盘前置 400。
    wc = working_copy_path(repo)
    wc_resolved = wc.resolve()
    for rel in bundle.files:
        try:
            (wc / rel).resolve().relative_to(wc_resolved)
        except ValueError:
            bundle.errors.append(f"导出路径越界:{rel}(登录态名称含非法路径字符,请改名后重试)")
    if bundle.errors:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"errors": bundle.errors})
    for rel, content in bundle.files.items():
        dest = wc / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    commit_msg = payload.commit_message or f"Web自动化导出 {s.name} {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    try:
        result = push_files(repo, sorted(bundle.files), payload.branch, commit_msg)
    except NothingToCommit as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, {"stage": e.stage, "error": e.message})
    except PushConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, {"stage": e.stage, "error": e.message})
    except GitError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, {"stage": e.stage, "error": e.message})
    return {**result.model_dump(), "files": sorted(bundle.files)}
