"""HTTP Mock 实例 API(计划 13 T6:实例 CRUD + start/stop;规则/命中组端点 Task 7 补)。

权限矩阵(复用 ensure_project_access,admin 直通 owner):
- viewer 读(list/get);editor 及以上写(create/update/delete/start/stop)。
- 404=不存在/软删/非项目成员(不泄漏存在性);403=成员但角色不足;409=状态冲突;400=入参/端口预检失败。
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.mock_service import supervisor
from app.models import MockInstance, Project, User
from app.permissions import ensure_project_access
from app.schemas import MockInstanceOut, MockInstancePatch, MockInstanceSave

router = APIRouter(prefix="/api", tags=["mock"], dependencies=[Depends(get_current_user)])


def _get_project(db: Session, project_id: int) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    return p


def _get_instance(db: Session, current: User, instance_id: int, min_role: str) -> MockInstance:
    """取行闸(模式同 app_scripts._get_script):404=不存在或已软删(不泄漏存在性),403=成员但角色不足。"""
    inst = db.get(MockInstance, instance_id)
    if inst is None or inst.is_deleted:
        raise HTTPException(404, "mock instance not found")
    ensure_project_access(db, current, inst.project_id, min_role)
    return inst


def _ensure_port_free(db: Session, port: int, exclude_id: int | None = None) -> None:
    """端口预检:库内查重(全表含软删行=端口预留)+ bind 试绑 → 400。"""
    q = db.query(MockInstance).filter(MockInstance.port == port)
    if exclude_id is not None:
        q = q.filter(MockInstance.id != exclude_id)
    if q.first() is not None:
        raise HTTPException(400, f"端口 {port} 已被实例占用")
    if not supervisor.bind_ok(port):
        raise HTTPException(400, f"端口 {port} 被外部进程占用")


@router.post("/projects/{project_id}/mock-instances", response_model=MockInstanceOut, status_code=201)
def create_instance(project_id: int, payload: MockInstanceSave, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    _get_project(db, project_id)
    ensure_project_access(db, current, project_id, "editor")
    name = payload.name.strip()
    if not name:
        raise HTTPException(400, "实例名称不能为空")
    port = payload.port
    if port is None:
        try:
            port = supervisor.alloc_free_port(db)  # None=范围内自动分配(库内已用口全部跳过)
        except ValueError as e:
            raise HTTPException(400, str(e))
    else:
        _ensure_port_free(db, port)
    inst = MockInstance(project_id=project_id, name=name, description=payload.description,
                        port=port, token=uuid4().hex, cors_enabled=payload.cors_enabled,
                        default_status=payload.default_status, default_body=payload.default_body,
                        desired="stopped", status="stopped",
                        created_by=current.id, updated_by=current.id)
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


@router.get("/projects/{project_id}/mock-instances", response_model=list[MockInstanceOut])
def list_instances(project_id: int, db: Session = Depends(get_db),
                   current: User = Depends(get_current_user)):
    _get_project(db, project_id)
    ensure_project_access(db, current, project_id, "viewer")
    return (db.query(MockInstance)
            .filter(MockInstance.project_id == project_id, MockInstance.is_deleted.is_(False))
            .order_by(MockInstance.id.desc()).all())


@router.get("/mock-instances/{instance_id}", response_model=MockInstanceOut)
def get_instance(instance_id: int, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    return _get_instance(db, current, instance_id, "viewer")


@router.put("/mock-instances/{instance_id}", response_model=MockInstanceOut)
def update_instance(instance_id: int, payload: MockInstancePatch, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "editor")
    if payload.port is not None and payload.port != inst.port:
        if inst.status not in ("stopped", "error"):  # 运行中/启动中锁端口(改口=换 base_url)
            raise HTTPException(409, "实例运行中不能修改端口,请先停止")
        _ensure_port_free(db, payload.port, exclude_id=inst.id)
        inst.port = payload.port
    if payload.name is not None:
        inst.name = payload.name
    if payload.description is not None:
        inst.description = payload.description
    if payload.cors_enabled is not None:
        inst.cors_enabled = payload.cors_enabled
    if payload.default_status is not None:
        inst.default_status = payload.default_status
    if payload.default_body is not None:
        inst.default_body = payload.default_body
    inst.updated_by = current.id
    db.commit()
    db.refresh(inst)
    return inst


@router.delete("/mock-instances/{instance_id}", status_code=204)
def delete_instance(instance_id: int, db: Session = Depends(get_db),
                    current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "editor")
    if inst.status in ("running", "starting"):
        raise HTTPException(409, "先停止实例再删除")
    inst.is_deleted = True  # 软删;端口行仍预留(alloc_free_port/查重都含软删行)
    inst.updated_by = current.id
    db.commit()


@router.post("/mock-instances/{instance_id}/start", response_model=MockInstanceOut)
def start_instance(instance_id: int, db: Session = Depends(get_db),
                   current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "editor")
    supervisor.start_instance(db, inst)
    db.commit()
    db.refresh(inst)
    return inst   # status 可能是 running|error(error 时前端展示 error_message)


@router.post("/mock-instances/{instance_id}/stop", response_model=MockInstanceOut)
def stop_instance(instance_id: int, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "editor")
    supervisor.stop_instance(db, inst)
    db.commit()
    db.refresh(inst)
    return inst
