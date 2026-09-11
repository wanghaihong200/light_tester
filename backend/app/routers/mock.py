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
from app.models import MockHit, MockInstance, MockRule, MockRuleGroup, Project, User
from app.permissions import ensure_project_access
from app.schemas import (MockGroupReorderBody, MockHitDetailOut, MockHitOut, MockInstanceOut,
                         MockInstancePatch, MockInstanceSave, MockReorderBody, MockRuleGroupOut,
                         MockRuleGroupPatch, MockRuleGroupSave, MockRuleOut, MockRulePatch,
                         MockRuleSave)

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


# ---------- 规则组(计划 15 T6:组承载 method+路径,组间/组内两级有序) ----------

def _validate_rule_payload(method: str, path_template: str) -> None:
    """规则载荷校验:method(已大写化)须 ∈ HTTP_METHODS,路径模板校验错误透传 → 400 列表合并报错。"""
    errs: list[str] = []
    if method not in matching.HTTP_METHODS:
        errs.append(f"不支持的 HTTP 方法: {method}")
    errs.extend(matching.validate_path_template(path_template))
    if errs:
        raise HTTPException(400, "; ".join(errs))


def _get_group(db: Session, current: User, group_id: int, min_role: str) -> MockRuleGroup:
    """行闸同 _get_instance:404=不存在或已软删(不泄漏存在性),403=成员但角色不足。"""
    g = db.get(MockRuleGroup, group_id)
    if g is None or g.is_deleted:
        raise HTTPException(404, "mock rule group not found")
    _get_instance(db, current, g.instance_id, min_role)
    return g


def _validate_route(db: Session, instance_id: int, method: str, path_template: str,
                    exclude_id: int | None = None) -> None:
    """组路由校验:method∈表+模板合法,且同实例内(未删)method+path_template 唯一 → 400。"""
    _validate_rule_payload(method, path_template)
    q = (db.query(MockRuleGroup)
         .filter(MockRuleGroup.instance_id == instance_id, MockRuleGroup.method == method,
                 MockRuleGroup.path_template == path_template, MockRuleGroup.is_deleted.is_(False)))
    if exclude_id is not None:
        q = q.filter(MockRuleGroup.id != exclude_id)
    if q.first() is not None:
        raise HTTPException(400, f"该实例下已存在 {method} {path_template} 的规则组")


def _groups_with_rules(db: Session, instance_id: int) -> list[tuple[MockRuleGroup, list]]:
    """实例下未删组(组间序)+ 各组未删规则(组内序),一次两条查询拼装。"""
    groups = (db.query(MockRuleGroup)
              .filter(MockRuleGroup.instance_id == instance_id, MockRuleGroup.is_deleted.is_(False))
              .order_by(MockRuleGroup.sort_order.asc(), MockRuleGroup.id.asc()).all())
    rules_by_group: dict[int, list] = {}
    for r in (db.query(MockRule)
              .filter(MockRule.instance_id == instance_id, MockRule.is_deleted.is_(False))
              .order_by(MockRule.sort_order.asc(), MockRule.id.asc()).all()):
        rules_by_group.setdefault(r.group_id, []).append(r)
    return [(g, rules_by_group.get(g.id, [])) for g in groups]


def _group_out(db: Session, g: MockRuleGroup) -> MockRuleGroupOut:
    """组 Out 带 rules 内嵌(pydantic 无 from_attributes 嵌套来源,手工组)。"""
    rules = (db.query(MockRule)
             .filter(MockRule.group_id == g.id, MockRule.is_deleted.is_(False))
             .order_by(MockRule.sort_order.asc(), MockRule.id.asc()).all())
    base = MockRuleGroupOut.model_validate(g)
    return base.model_copy(update={"rules": [MockRuleOut.model_validate(r) for r in rules]})


@router.post("/mock-instances/{instance_id}/rule-groups", response_model=MockRuleGroupOut,
             status_code=201)
def create_group(instance_id: int, payload: MockRuleGroupSave, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "editor")
    method = payload.method.strip().upper()  # 入参小写归一为大写落库
    _validate_route(db, inst.id, method, payload.path_template)
    # 含软删行一起取最大:实例内组 sort_order 不重号,匹配序稳定
    max_order = (db.query(func.max(MockRuleGroup.sort_order))
                 .filter(MockRuleGroup.instance_id == inst.id).scalar()) or 0
    g = MockRuleGroup(instance_id=inst.id, method=method, path_template=payload.path_template,
                      description=payload.description, enabled=payload.enabled,
                      sort_order=max_order + 1, created_by=current.id, updated_by=current.id)
    db.add(g)
    db.commit()
    db.refresh(g)
    return _group_out(db, g)


@router.get("/mock-instances/{instance_id}/rule-groups", response_model=list[MockRuleGroupOut])
def list_groups(instance_id: int, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "viewer")
    return [_group_out(db, g) for g, _ in _groups_with_rules(db, inst.id)]


@router.put("/mock-rule-groups/{group_id}", response_model=MockRuleGroupOut)
def update_group(group_id: int, payload: MockRuleGroupPatch, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    g = _get_group(db, current, group_id, "editor")
    changed = payload.model_dump(exclude_unset=True)  # 部分PATCH:description 显式传 null=清空
    if "method" in changed or "path_template" in changed:
        # 判空针对"实际将落库"的合并值,校验/落库同一判定:method/path_template 不接受
        # 显式 null(无清空语义)也不接受空串(死路由)→ 400,不得穿透成 500 或脏写
        method = changed.get("method")
        path_template = changed.get("path_template")
        if ("method" in changed and not (method and method.strip())) or \
                ("path_template" in changed and not (path_template and path_template.strip())):
            raise HTTPException(400, "method/路径不能为空,且不接受 null")
        _validate_route(db, g.instance_id, (method or g.method).strip().upper(),
                        path_template if path_template is not None else g.path_template,
                        exclude_id=g.id)
    if "method" in changed:
        g.method = changed["method"].strip().upper()
    if "path_template" in changed:
        g.path_template = changed["path_template"]
    if "description" in changed:
        g.description = changed["description"]  # 仅 description 保留"显式 null=清空"
    if changed.get("enabled") is not None:
        g.enabled = changed["enabled"]  # enabled 为非空布尔列,null 按未提供处理
    g.updated_by = current.id
    db.commit()
    db.refresh(g)
    return _group_out(db, g)


@router.delete("/mock-rule-groups/{group_id}", status_code=204)
def delete_group(group_id: int, db: Session = Depends(get_db),
                 current: User = Depends(get_current_user)):
    g = _get_group(db, current, group_id, "editor")
    g.is_deleted = True
    g.updated_by = current.id
    for r in (db.query(MockRule)
              .filter(MockRule.group_id == g.id, MockRule.is_deleted.is_(False)).all()):
        r.is_deleted = True  # 组亡规则亡(软删;命中记录 rule_id 仍可追溯)
        r.updated_by = current.id
    db.commit()


@router.put("/mock-instances/{instance_id}/rule-groups/reorder",
            response_model=list[MockRuleGroupOut])
def reorder_groups(instance_id: int, payload: MockGroupReorderBody,
                   db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "editor")
    groups = (db.query(MockRuleGroup)
              .filter(MockRuleGroup.instance_id == inst.id, MockRuleGroup.is_deleted.is_(False)).all())
    by_id = {g.id: g for g in groups}
    # group_ids=全量新序:集合不等(缺/多/跨实例 id)或入参含重复 → 400
    if len(payload.group_ids) != len(set(payload.group_ids)) or set(payload.group_ids) != set(by_id):
        raise HTTPException(400, "group_ids 必须恰好是实例下全部规则组的 id 全量新序")
    for idx, gid in enumerate(payload.group_ids):
        by_id[gid].sort_order = idx
        by_id[gid].updated_by = current.id
    db.commit()
    return [_group_out(db, by_id[gid]) for gid in payload.group_ids]


@router.put("/mock-rule-groups/{group_id}/rules/reorder", response_model=list[MockRuleOut])
def reorder_group_rules(group_id: int, payload: MockReorderBody, db: Session = Depends(get_db),
                        current: User = Depends(get_current_user)):
    g = _get_group(db, current, group_id, "editor")
    rules = (db.query(MockRule)
             .filter(MockRule.group_id == g.id, MockRule.is_deleted.is_(False)).all())
    by_id = {r.id: r for r in rules}
    # rule_ids=组内全量新序:集合不等(缺/多/他组 id)或入参含重复 → 400
    if len(payload.rule_ids) != len(set(payload.rule_ids)) or set(payload.rule_ids) != set(by_id):
        raise HTTPException(400, "rule_ids 必须恰好是该组下全部规则的 id 全量新序")
    for idx, rid in enumerate(payload.rule_ids):
        by_id[rid].sort_order = idx
        by_id[rid].updated_by = current.id
    db.commit()
    return [by_id[rid] for rid in payload.rule_ids]


# ---------- 规则(挂组:只存条件+响应,method/path 由组承载) ----------

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
    group = db.get(MockRuleGroup, payload.group_id)
    if group is None or group.is_deleted:
        raise HTTPException(404, "mock rule group not found")
    if group.instance_id != inst.id:
        raise HTTPException(400, "rule group 不属于该实例")
    # 含软删行一起取最大:组内 sort_order 不重号,匹配序稳定
    max_order = (db.query(func.max(MockRule.sort_order))
                 .filter(MockRule.group_id == group.id).scalar()) or 0
    rule = MockRule(
        instance_id=inst.id, group_id=group.id,
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
    rules = (db.query(MockRule)
             .filter(MockRule.instance_id == inst.id, MockRule.is_deleted.is_(False)).all())
    groups = {g.id: g.sort_order for g in (db.query(MockRuleGroup)
              .filter(MockRuleGroup.instance_id == inst.id, MockRuleGroup.is_deleted.is_(False))
              .all())}
    # 平铺序=组间序再组内序;孤儿(软删组)历史规则沉底,仅测试兜底用
    rules.sort(key=lambda r: (groups.get(r.group_id, 1 << 30), r.sort_order, r.id))
    return rules


@router.put("/mock-rules/{rule_id}", response_model=MockRuleOut)
def update_rule(rule_id: int, payload: MockRulePatch, db: Session = Depends(get_db),
                current: User = Depends(get_current_user)):
    rule = _get_rule(db, current, rule_id, "editor")
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


# ---------- 命中组(计划 13 T7;计划 15 T7 四态过滤 + 按组归组过滤) ----------

def _hit_in_group(hit: MockHit, group: MockRuleGroup, rule_ids: set[int]) -> bool:
    if hit.rule_id in rule_ids:  # 命中行(规则可能已软删,rule_id 仍追溯)
        return True
    # 未命中行:方法相同且实际路径能被组模板匹配 = 打过这个路由但没接住(兜底/透传失败),归入组视角
    return (not hit.matched and group.method.upper() == hit.method.upper()
            and matching.match_path(group.path_template, hit.path) is not None)


@router.get("/mock-instances/{instance_id}/hits", response_model=list[MockHitOut])
def list_hits(instance_id: int, filter: str = Query("all"),
              group_id: int | None = Query(None), limit: int = Query(200, ge=1, le=1000),
              db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    inst = _get_instance(db, current, instance_id, "viewer")
    if filter not in ("all", "matched", "unmatched", "forwarded"):
        raise HTTPException(400, "filter 只支持 all|matched|unmatched|forwarded")
    q = db.query(MockHit).filter(MockHit.instance_id == inst.id)
    if filter == "matched":
        q = q.filter(MockHit.matched.is_(True))
    elif filter == "unmatched":
        q = q.filter(MockHit.matched.is_(False), MockHit.outcome == "fallback")
    elif filter == "forwarded":
        q = q.filter(MockHit.outcome == "forwarded")
    rows = q.order_by(MockHit.id.desc()).limit(1000).all()  # 表有 1000 滚动上限,全量进内存做组归因
    if group_id is not None:
        g = _get_group(db, current, group_id, "viewer")
        rule_ids = {r.id for r in db.query(MockRule.id)
                    .filter(MockRule.group_id == g.id).all()}  # 含软删:历史命中仍可归组
        rows = [h for h in rows if _hit_in_group(h, g, rule_ids)]
    return rows[:limit]


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
