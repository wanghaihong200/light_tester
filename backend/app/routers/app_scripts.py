"""APP自动化脚本 API(独立域,不碰 ui_scripts)。用例体 = SoloPi 原生 JSON 唯一事实源,原样存储。"""
import json
import subprocess
from datetime import datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.app_automation import devices, solopi_cli
from app.app_automation.appium_export import collect_export_bundle
from app.app_automation.case_schema import high_risk_actions, validate_case
from app.automation_repo import require_repo
from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.git_service import (
    GitError,
    NothingToCommit,
    PushConflict,
    push_files,
    sync_repo,
    working_copy_path,
)
from app.models import AppScript, Project, User
from app.permissions import ensure_project_access
from app.schemas import AppScriptOut

router = APIRouter(prefix="/api", tags=["app-scripts"], dependencies=[Depends(get_current_user)])


def _get_project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    return p


def _get_script(db: Session, current: User, script_id: int, min_role: str) -> AppScript:
    """Task 8/12 复用的取行闸:404=不存在或已软删(不泄漏存在性),403=成员但角色不足。"""
    s = db.get(AppScript, script_id)
    if s is None or s.is_deleted:
        raise HTTPException(404, "script not found")
    ensure_project_access(db, current, s.project_id, min_role)
    return s


def _check_case(case: dict, allow_high_risk: bool) -> None:
    errs = validate_case(case)
    if errs:
        raise HTTPException(400, "用例不合法: " + ";".join(errs[:3]))
    risky = high_risk_actions(case)
    if risky and not allow_high_risk:
        raise HTTPException(400, f"用例含高危动作({','.join(risky)}),需勾选「允许高危动作」确认")


class AppScriptSave(BaseModel):
    name: str | None = None
    description: str | None = None
    case: dict
    allow_high_risk: bool = False


class AppScriptPatch(BaseModel):
    name: str | None = None
    description: str | None = None
    case: dict | None = None
    allow_high_risk: bool = False


@router.post("/projects/{project_id}/app-scripts", response_model=AppScriptOut, status_code=201)
def create_script(project_id: int, payload: AppScriptSave, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    _get_project(db, project_id)
    ensure_project_access(db, current, project_id, "editor")
    _check_case(payload.case, payload.allow_high_risk)
    s = AppScript(project_id=project_id,
                  name=payload.name or str(payload.case.get("caseName") or "") or "未命名用例",
                  description=payload.description, case_json=payload.case,
                  app_package=str(payload.case.get("targetAppPackage") or ""),
                  created_by=current.id, updated_by=current.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/projects/{project_id}/app-scripts", response_model=list[AppScriptOut])
def list_scripts(project_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _get_project(db, project_id)
    ensure_project_access(db, current, project_id, "viewer")
    return (db.query(AppScript)
            .filter(AppScript.project_id == project_id, AppScript.is_deleted.is_(False))
            .order_by(AppScript.id.desc()).all())


@router.get("/app-scripts/{script_id}", response_model=AppScriptOut)
def get_script(script_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    return _get_script(db, current, script_id, "viewer")


@router.put("/app-scripts/{script_id}", response_model=AppScriptOut)
def update_script(script_id: int, payload: AppScriptPatch, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    s = _get_script(db, current, script_id, "editor")
    if payload.case is not None:
        _check_case(payload.case, payload.allow_high_risk)
        s.case_json = payload.case
        s.app_package = str(payload.case.get("targetAppPackage") or "")
    if payload.name is not None:
        s.name = payload.name
    if payload.description is not None:
        s.description = payload.description
    s.updated_by = current.id
    db.commit()
    db.refresh(s)
    return s


@router.delete("/app-scripts/{script_id}", status_code=204)
def delete_script(script_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    s = _get_script(db, current, script_id, "editor")
    s.is_deleted = True
    s.updated_by = current.id
    db.commit()


_IMPORT_MAX_BYTES = 1024 * 1024


class DeviceImport(BaseModel):
    serial: str
    file_name: str
    name: str | None = None
    allow_high_risk: bool = False


def _create_from_case(db: Session, current: User, project_id: int, case: dict,
                      name: str | None, allow_high_risk: bool) -> AppScript:
    _check_case(case, allow_high_risk)
    s = AppScript(project_id=project_id,
                  name=name or str(case.get("caseName") or "") or "未命名用例",
                  case_json=case, app_package=str(case.get("targetAppPackage") or ""),
                  created_by=current.id, updated_by=current.id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.get("/projects/{project_id}/app-scripts/device-cases")
def device_cases(project_id: int, serial: str, dir_: str | None = Query(None, alias="dir"),
                 db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    _get_project(db, project_id)
    ensure_project_access(db, current, project_id, "editor")  # 读设备=写会话语义(对齐录制流闸 editor)
    try:
        return devices.list_device_cases(serial, dir_ or devices.HARNESS_IMPORT_DIR)
    except (RuntimeError, subprocess.SubprocessError, OSError) as e:
        raise HTTPException(400, f"设备读取失败: {e}")


@router.post("/projects/{project_id}/app-scripts/import-device", response_model=AppScriptOut, status_code=201)
def import_device(project_id: int, payload: DeviceImport, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    _get_project(db, project_id)
    ensure_project_access(db, current, project_id, "editor")
    dest = settings.app_data_dir / "imports" / payload.file_name
    try:
        devices.pull_device_case(payload.serial, payload.file_name, dest)
        case = json.loads(dest.read_text(encoding="utf-8-sig"))
    except (RuntimeError, subprocess.SubprocessError, OSError) as e:
        raise HTTPException(400, f"拉取失败: {e}")
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        raise HTTPException(400, f"文件不是合法 JSON: {payload.file_name}")
    return _create_from_case(db, current, project_id, case, payload.name, payload.allow_high_risk)


@router.post("/projects/{project_id}/app-scripts/import-upload", response_model=AppScriptOut, status_code=201)
def import_upload(project_id: int, file: UploadFile, name: str | None = Form(None),
                  allow_high_risk: bool = Form(False), db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    _get_project(db, project_id)
    ensure_project_access(db, current, project_id, "editor")
    raw = file.file.read(_IMPORT_MAX_BYTES + 1)
    if len(raw) > _IMPORT_MAX_BYTES:
        raise HTTPException(400, "用例文件超过 1MB 上限")
    try:
        case = json.loads(raw.decode("utf-8-sig"))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        raise HTTPException(400, "文件不是合法 JSON")
    return _create_from_case(db, current, project_id, case, name, allow_high_risk)


@router.get("/app-devices")
def app_devices(current: User = Depends(get_current_user)):
    """设备清单(登录即可读;设备无项目归属)。"""
    try:
        return devices.list_devices_detailed()
    except (RuntimeError, subprocess.SubprocessError, OSError) as e:
        raise HTTPException(400, f"adb 读取失败: {e}")


@router.get("/app-devices/{serial}/perf-items")
def app_device_perf_items(serial: str, current: User = Depends(get_current_user)):
    """perf 可采集项动态发现(perf-list;键名随设备/插件不同,勿硬编码)。"""
    try:
        payload = solopi_cli.perf_list(serial)
    except solopi_cli.CliError as e:
        raise HTTPException(400, e.message)
    items = payload.get("items") or payload.get("metrics") or payload.get("keys") or []
    # 冒烟实测(2026-09-08):items 每项是对象 {"key": "CPU", "name": …, "permissions": […]}。
    # dict 取 key 字段;非字典项兜底 str;dict 缺 key 过滤(不向前端吐 "None"/stringify 串)。
    return {"items": [str(i.get("key")) if isinstance(i, dict) else str(i)
                      for i in items
                      if not isinstance(i, dict) or i.get("key") is not None]}


class AppScriptExportRequest(BaseModel):
    branch: str
    commit_message: str | None = None


@router.post("/app-scripts/{script_id}/export")
def export_script(script_id: int, payload: AppScriptExportRequest, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    """翻译 SoloPi JSON 为 Appium pytest 产物并推送 kind=app 仓(对齐 ui_scripts export 语义)。"""
    s = _get_script(db, current, script_id, "viewer")  # 先可见性(非成员 404)
    ensure_project_access(db, current, s.project_id, "editor")  # 推外部仓 = editor
    bundle = collect_export_bundle(s.id, s.name, s.case_json)
    if bundle.errors:
        raise HTTPException(400, {"errors": bundle.errors})
    repo = require_repo(db, s.project_id, "app")
    try:
        sync_repo(repo)
    except GitError:
        pass  # 同步失败不阻断(push 内部 rebase 兜底;对齐计划 11 导出端点语义)
    # push_files 只 add 给定路径,产物必须先写入 working copy(计划 11 冒烟教训)。
    wc = working_copy_path(repo)
    for rel, content in bundle.files.items():
        dest = wc / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    commit_msg = payload.commit_message or f"APP自动化导出 {s.name} {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    try:
        result = push_files(repo, sorted(bundle.files), payload.branch, commit_msg)
    except NothingToCommit as e:
        raise HTTPException(400, {"stage": e.stage, "error": e.message})
    except PushConflict as e:
        raise HTTPException(409, {"stage": e.stage, "error": e.message})
    except GitError as e:
        raise HTTPException(409, {"stage": e.stage, "error": e.message})
    return {**result.model_dump(), "files": sorted(bundle.files)}
