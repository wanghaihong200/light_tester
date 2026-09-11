"""HTTP Mock 实例 API(计划 13 T6 实例 CRUD + start/stop;T7 规则组 + 命中组)。

权限矩阵(复用 ensure_project_access,admin 直通 owner):
- viewer 读(list/get);editor 及以上写(create/update/delete/start/stop/reorder/clear)。
- 404=不存在/软删/非项目成员(不泄漏存在性);403=成员但角色不足;409=状态冲突;400=入参/端口预检失败。
"""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.mock_service import matching, supervisor
from app.models import MockHit, MockInstance, MockRule, Project, User
from app.permissions import ensure_project_access
from app.schemas import (MockHitDetailOut, MockHitOut, MockInstanceOut, MockInstancePatch,
                         MockInstanceSave, MockReorderBody, MockRuleOut, MockRulePatch, MockRuleSave)

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


def _validate_passthrough(enabled: bool, url: str | None) -> tuple[bool, str | None]:
    """透传字段共用校验(create/update 同源,防漂移):
    strip 后空串落 None;开启透传必须非空;非空须 http(s):// 开头。"""
    url = (url or "").strip() or None
    if enabled and not url:
        raise HTTPException(400, "开启透传必须填写上游 base_url")
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(400, "上游 base_url 须以 http:// 或 https:// 开头")
    return enabled, url


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
    enabled, upstream = _validate_passthrough(payload.passthrough_enabled,
                                              payload.upstream_base_url)
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
                        passthrough_enabled=enabled, upstream_base_url=upstream,
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
    if payload.passthrough_enabled is not None or payload.upstream_base_url is not None:
        new_enabled = (payload.passthrough_enabled if payload.passthrough_enabled is not None
                       else inst.passthrough_enabled)
        new_url = (payload.upstream_base_url if payload.upstream_base_url is not None
                   else inst.upstream_base_url)
        inst.passthrough_enabled, inst.upstream_base_url = _validate_passthrough(new_enabled,
                                                                                 new_url)
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


# ---------- 规则组(计划 13 T7) ----------

def _validate_rule_payload(method: str, path_template: str) -> None:
    """规则载荷校验:method(已大写化)须 ∈ HTTP_METHODS,路径模板校验错误透传 → 400 列表合并报错。"""
    errs: list[str] = []
    if method not in matching.HTTP_METHODS:
        errs.append(f"不支持的 HTTP 方法: {method}")
    errs.extend(matching.validate_path_template(path_template))
    if errs:
        raise HTTPException(400, "; ".join(errs))


def _get_rule(db: Session, current: User, rule_id: int, min_role: str) -> MockRule:
    """行闸同 _get_instance:404=不存在或已软删(不泄漏存在性),403=成员但角色不足。"""
    rule = db.get(MockRule, rule_id)
    if rule is None or rule.is_deleted:
        raise HTTPException(404, "mock rule not found")
    _get_instance(db, current, rule.instance_id, min_role)
    return rule


@router.post("/mock-instances/{instance_id}/rules", response_model=MockRuleOut, status_code=201)
def create_rule(instance_id: int, payload: MockRuleSave, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "editor")
    method = payload.method.strip().upper()  # 入参小写归一为大写落库
    _validate_rule_payload(method, payload.path_template)
    # 含软删行一起取最大:实例内 sort_order 不重号,匹配序稳定
    max_order = (db.query(func.max(MockRule.sort_order))
                 .filter(MockRule.instance_id == inst.id).scalar()) or 0
    rule = MockRule(
        instance_id=inst.id, method=method, path_template=payload.path_template,
        conditions=[c.model_dump() for c in payload.conditions], enabled=payload.enabled,
        response_status=payload.response_status, response_headers=payload.response_headers,
        response_body=payload.response_body, enable_template=payload.enable_template,
        delay_ms=payload.delay_ms, timeout_enabled=payload.timeout_enabled,
        timeout_seconds=payload.timeout_seconds, sort_order=max_order + 1,
        created_by=current.id, updated_by=current.id)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/mock-instances/{instance_id}/rules", response_model=list[MockRuleOut])
def list_rules(instance_id: int, db: Session = Depends(get_db),
               current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "viewer")
    return (db.query(MockRule)
            .filter(MockRule.instance_id == inst.id, MockRule.is_deleted.is_(False))
            .order_by(MockRule.sort_order.asc(), MockRule.id.asc()).all())


@router.put("/mock-rules/{rule_id}", response_model=MockRuleOut)
def update_rule(rule_id: int, payload: MockRulePatch, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    rule = _get_rule(db, current, rule_id, "editor")
    if payload.method is not None or payload.path_template is not None:
        _validate_rule_payload(
            payload.method.strip().upper() if payload.method is not None else rule.method,
            payload.path_template if payload.path_template is not None else rule.path_template)
    if payload.method is not None:
        rule.method = payload.method.strip().upper()
    if payload.path_template is not None:
        rule.path_template = payload.path_template
    if payload.conditions is not None:
        rule.conditions = [c.model_dump() for c in payload.conditions]
    if payload.enabled is not None:
        rule.enabled = payload.enabled
    if payload.response_status is not None:
        rule.response_status = payload.response_status
    if payload.response_headers is not None:
        rule.response_headers = payload.response_headers
    if payload.response_body is not None:
        rule.response_body = payload.response_body
    if payload.enable_template is not None:
        rule.enable_template = payload.enable_template
    if payload.delay_ms is not None:
        rule.delay_ms = payload.delay_ms
    if payload.timeout_enabled is not None:
        rule.timeout_enabled = payload.timeout_enabled
    if payload.timeout_seconds is not None:
        rule.timeout_seconds = payload.timeout_seconds
    rule.updated_by = current.id
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/mock-rules/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    rule = _get_rule(db, current, rule_id, "editor")
    rule.is_deleted = True  # 软删(命中记录 rule_id 仍可追溯)
    rule.updated_by = current.id
    db.commit()


@router.put("/mock-instances/{instance_id}/rules/reorder", response_model=list[MockRuleOut])
def reorder_rules(instance_id: int, payload: MockReorderBody, db: Session = Depends(get_db),
                  current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "editor")
    rules = (db.query(MockRule)
             .filter(MockRule.instance_id == inst.id, MockRule.is_deleted.is_(False)).all())
    by_id = {r.id: r for r in rules}
    # rule_ids=全量新序:集合不等(缺/多/跨实例 id)或入参含重复 → 400
    if len(payload.rule_ids) != len(set(payload.rule_ids)) or set(payload.rule_ids) != set(by_id):
        raise HTTPException(400, "rule_ids 必须恰好是实例下全部规则的 id 全量新序")
    for idx, rid in enumerate(payload.rule_ids):
        by_id[rid].sort_order = idx
    db.commit()
    return [by_id[rid] for rid in payload.rule_ids]


# ---------- 命中组(计划 13 T7) ----------

@router.get("/mock-instances/{instance_id}/hits", response_model=list[MockHitOut])
def list_hits(instance_id: int, filter: str = Query("all"),
              limit: int = Query(200, ge=1, le=1000), db: Session = Depends(get_db),
              current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "viewer")
    if filter not in ("all", "matched", "unmatched"):
        raise HTTPException(400, "filter 只支持 all|matched|unmatched")
    q = db.query(MockHit).filter(MockHit.instance_id == inst.id)
    if filter == "matched":
        q = q.filter(MockHit.matched.is_(True))
    elif filter == "unmatched":
        q = q.filter(MockHit.matched.is_(False))
    return q.order_by(MockHit.id.desc()).limit(limit).all()


@router.get("/mock-hits/{hit_id}", response_model=MockHitDetailOut)
def get_hit(hit_id: int, db: Session = Depends(get_db),
            current: User = Depends(get_current_user)):
    hit = db.get(MockHit, hit_id)
    if hit is None:
        raise HTTPException(404, "mock hit not found")
    _get_instance(db, current, hit.instance_id, "viewer")
    return hit


@router.delete("/mock-instances/{instance_id}/hits", status_code=204)
def clear_hits(instance_id: int, db: Session = Depends(get_db),
               current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "editor")
    db.query(MockHit).filter(MockHit.instance_id == inst.id).delete(synchronize_session=False)
    db.commit()  # 硬删全清(命中表 append-only,这是唯一删除入口)
