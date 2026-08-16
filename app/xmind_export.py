"""生成 .xmind 导出文件(XMind Zen 格式:zip 内含 content.json + metadata.json)。

树形约定与前端适配器一致:子模块在前、功能点在后;用例为叶子。
优先级映射为 XMind 官方 marker:P0 -> priority-1,P1 -> priority-2,P2 -> priority-3。
用例的前置条件/步骤/备注/执行结果拼进 topic 的 notes 纯文本。
"""

import io
import json
import uuid
import zipfile

from sqlalchemy.orm import Session, selectinload

from app.models import Case, FeaturePoint, Module, Project

_PRIORITY_MARKERS = {"P0": "priority-1", "P1": "priority-2", "P2": "priority-3"}


def _topic(title: str, *, children=None, markers=None, notes=None) -> dict:
    topic: dict = {"id": uuid.uuid4().hex, "class": "topic", "title": title}
    if markers:
        topic["markers"] = [{"markerId": m} for m in markers]
    if notes:
        topic["notes"] = {"plain": {"content": notes}}
    if children:
        topic["children"] = {"attached": children}
    return topic


def _case_notes(case: Case) -> str:
    lines: list[str] = []
    if case.precondition:
        lines.append(f"前置条件:{case.precondition}")
    for step in case.steps:
        lines.append(f"步骤{step.step_no}: {step.action} → 预期: {step.expected}")
    if case.remark:
        lines.append(f"备注:{case.remark}")
    if case.executed_pass is True:
        lines.append("执行结果:通过")
    elif case.executed_pass is False:
        lines.append("执行结果:未通过")
    else:
        lines.append("执行结果:未执行")
    return "\n".join(lines)


def build_xmind_bytes(db: Session, project: Project) -> bytes:
    # 三次批量查询组树,避免递归 N+1(与 get_tree 同风格)
    modules = (
        db.query(Module)
        .filter(Module.project_id == project.id)
        .order_by(Module.sort_order, Module.id)
        .all()
    )
    module_ids = [m.id for m in modules]
    fps: list[FeaturePoint] = []
    cases: list[Case] = []
    if module_ids:
        fps = (
            db.query(FeaturePoint)
            .filter(FeaturePoint.module_id.in_(module_ids))
            .order_by(FeaturePoint.sort_order, FeaturePoint.id)
            .all()
        )
    fp_ids = [f.id for f in fps]
    if fp_ids:
        cases = (
            db.query(Case)
            .filter(Case.feature_point_id.in_(fp_ids))
            .options(selectinload(Case.steps))
            .order_by(Case.sort_order, Case.id)
            .all()
        )

    children_by_parent: dict[int | None, list[Module]] = {}
    for m in modules:
        children_by_parent.setdefault(m.parent_id, []).append(m)
    fps_by_module: dict[int, list[FeaturePoint]] = {}
    for f in fps:
        fps_by_module.setdefault(f.module_id, []).append(f)
    cases_by_fp: dict[int, list[Case]] = {}
    for c in cases:
        cases_by_fp.setdefault(c.feature_point_id, []).append(c)

    def case_topic(c: Case) -> dict:
        markers = [_PRIORITY_MARKERS[c.priority]] if c.priority in _PRIORITY_MARKERS else None
        return _topic(c.title, markers=markers, notes=_case_notes(c))

    def module_topic(m: Module) -> dict:
        kids = [module_topic(cm) for cm in children_by_parent.get(m.id, [])]
        kids += [_topic(f.name, children=[case_topic(c) for c in cases_by_fp.get(f.id, [])]) for f in fps_by_module.get(m.id, [])]
        return _topic(m.name, children=kids or None)

    root = _topic(project.name, children=[module_topic(m) for m in children_by_parent.get(None, [])] or None)
    content = [{"id": uuid.uuid4().hex, "class": "sheet", "title": "Sheet 1", "rootTopic": root}]
    metadata = {"creator": {"name": "test-platform", "version": "1.0"}}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", json.dumps(content, ensure_ascii=False))
        z.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False))
    return buf.getvalue()
