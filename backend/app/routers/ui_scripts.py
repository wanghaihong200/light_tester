# UI自动化脚本 CRUD:录制产出的步骤 DSL 文档的增删改查
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Project, UiScript, User
from app.permissions import ensure_project_access
from app.schemas import UiScriptOut, UiScriptSave

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
