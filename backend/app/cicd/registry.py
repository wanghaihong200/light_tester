"""接口用例注册表增量合并:按 仓×分支×case_type 合并扫描结果,消失的方法标 stale、重现的复活。"""


def sync_registry(db, project_id: int, branch: str, scanned: list[dict],
                  commit: str | None, case_type: str = "api") -> dict:
    """注册表增量合并(ADR-0012 决策4/ADR-0013):按 仓×分支×case_type 圈定,
    消失的标 stale、重现的复活;stale 判定不跨用例域串味。"""
    from app.models import InterfaceCase

    existing = {(c.class_name, c.method): c for c in db.query(InterfaceCase).filter_by(
        project_id=project_id, branch=branch, case_type=case_type, is_deleted=False)}
    seen: set[tuple[str, str]] = set()
    added = 0
    for item in scanned:
        key = (item["class_name"], item["method"])
        seen.add(key)
        row = existing.get(key)
        if row is None:
            db.add(InterfaceCase(project_id=project_id, branch=branch,
                                 class_name=item["class_name"], method=item["method"],
                                 status="active", framework=item["framework"],
                                 file_path=item["file_path"], last_commit=commit,
                                 case_type=case_type, title=item.get("title"),
                                 markers=item.get("markers") or []))
            added += 1
        else:
            row.status = "active"
            row.framework = item["framework"]
            row.file_path = item["file_path"]
            row.last_commit = commit
            row.title = item.get("title")
            row.markers = item.get("markers") or []
    stale = sum(1 for key, row in existing.items() if key not in seen and row.status != "stale")
    for key, row in existing.items():
        if key not in seen:
            row.status = "stale"
    db.commit()
    total = db.query(InterfaceCase).filter_by(project_id=project_id, branch=branch,
                                              case_type=case_type, is_deleted=False).count()
    active = db.query(InterfaceCase).filter_by(project_id=project_id, branch=branch,
                                               case_type=case_type, status="active",
                                               is_deleted=False).count()
    return {"total": total, "active": active, "stale": stale, "added": added}
