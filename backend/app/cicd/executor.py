"""触发编排(ADR-0012 决策 1/4):sync 切分支 → 新鲜度 → 物料过滤/快照 → 确保 job → 触发 build。

顺序即语义:先 checkout 计划分支再做新鲜度/物料判定,保证「执行分支=工作区分支」;
client 参数供测试注入 FakeJenkins,生产恒 None(按连接配置现建)。
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import git_service
from app.cicd import freshness, jenkins_client, jenkins_job
from app.models import AutomationRepo, CiRun, ExecutionPlan, InterfaceCase, JenkinsConnection, User

PLAN_KIND_TO_REPO = {"ui": "web", "api": "api"}


def client_from(conn: JenkinsConnection) -> jenkins_client.JenkinsClient:
    return jenkins_client.JenkinsClient(conn.base_url, conn.api_user, conn.api_token)


def repo_for(db: Session, project_id: int, kind: str) -> AutomationRepo:
    kind_repo = PLAN_KIND_TO_REPO[kind]
    repo = db.query(AutomationRepo).filter_by(project_id=project_id, kind=kind_repo,
                                              is_deleted=False).first()
    if repo is None:
        raise HTTPException(400, f"项目未配置 {kind_repo} 自动化仓,请先在「自动化工程」配置")
    return repo


def _resolve_selection(db: Session, plan: ExecutionPlan, ws) -> tuple[list[dict], str]:
    """物料校验:ui 项查 Web用例注册表 active + 文件存在兜底(ADR-0013);api 项查注册表 active。
    返回 (快照项(缺失项标 skipped/skip_reason), 可执行 SELECTION 串)。"""
    snap: list[dict] = []
    valid_ui: list[str] = []
    valid_api: list[tuple[str, str]] = []
    if plan.kind == "ui":
        rows = {(c.class_name, c.method): c for c in db.query(InterfaceCase).filter_by(
            project_id=plan.project_id, branch=plan.branch, case_type="web", is_deleted=False)}
        for it in plan.selection or []:
            fp, fn = it.get("file_path"), it.get("function")
            row = rows.get((fp, fn))
            if row is None or row.status != "active":
                entry = {**it, "skipped": True, "skip_reason": "stale"}
            else:
                file_ok = bool(fp) and (ws / fp).resolve().is_relative_to(ws.resolve()) \
                    and (ws / fp).exists()
                entry = {**it, "skipped": not file_ok}
                if not file_ok:
                    entry["skip_reason"] = "file_missing"
            snap.append(entry)
            if not entry["skipped"]:
                valid_ui.append(f"{fp}::{fn}")
    else:
        rows = {(c.class_name, c.method): c for c in db.query(InterfaceCase).filter_by(
            project_id=plan.project_id, branch=plan.branch, is_deleted=False)}
        for it in plan.selection or []:
            row = rows.get((it.get("class_name"), it.get("method")))
            ok = row is not None and row.status == "active"
            entry = {**it, "skipped": not ok}
            if not ok:
                entry["skip_reason"] = "stale"
            snap.append(entry)
            if ok:
                valid_api.append((it["class_name"], it["method"]))
    if plan.kind == "ui":
        selection_arg = " ".join(valid_ui)
    else:
        grouped: dict[str, list[str]] = {}
        for cls, method in valid_api:
            grouped.setdefault(cls, []).append(method)
        selection_arg = ",".join(f"{cls}#{'+'.join(ms)}" for cls, ms in grouped.items())
    return snap, selection_arg


def trigger_plan(db: Session, user: User, plan: ExecutionPlan, *, confirm_stale: bool,
                 client: jenkins_client.JenkinsClient | None = None) -> CiRun:
    if not plan.selection:
        raise HTTPException(400, "空计划不可触发,请先勾选用例")
    conn = db.query(JenkinsConnection).first()
    if conn is None:
        raise HTTPException(400, "Jenkins 连接未配置,请联系管理员")
    repo = repo_for(db, plan.project_id, plan.kind)
    try:
        git_service.sync_repo(repo, plan.branch)  # fetch + checkout 计划分支 + reset --hard
    except git_service.GitError as e:
        raise HTTPException(400, f"分支切换失败: {e}") from e
    fresh = freshness.check_freshness(repo, plan.branch)
    if fresh["stale"] and not confirm_stale:
        raise HTTPException(409, {"message": "仓里有新代码未同步到远端,是否仍按远端现状(老代码)执行?",
                                  "freshness": fresh})
    ws = git_service.working_copy_path(repo)
    snap, selection_arg = _resolve_selection(db, plan, ws)
    if not selection_arg:
        hint = ("请先扫描该分支,或编辑计划改选用例所在分支" if plan.kind == "ui"
                else "请先导出脚本/扫描注册表到该分支")
        raise HTTPException(400, f"计划分支「{plan.branch}」上无所选用例的任何物料,{hint}")
    own = client or client_from(conn)
    try:
        name = jenkins_job.job_name(plan.project_id, plan.kind)
        if not own.job_exists(name):
            own.create_pipeline_job(name, jenkins_job.build_job_config(jenkins_job.PIPELINE_SCRIPT))
        params = {"REPO_URL": jenkins_job.rewrite_gitlab_url(repo.repo_url, conn.gitlab_exposed_base),
                  "BRANCH": plan.branch, "KIND": plan.kind, "SELECTION": selection_arg,
                  "CREDENTIALS_ID": conn.credential_id}
        build_number, build_url = own.trigger_build(name, params)
    except jenkins_client.JenkinsError as e:
        raise HTTPException(502, f"Jenkins 调用失败: {e}") from e
    run = CiRun(project_id=plan.project_id, plan_id=plan.id, plan_name=plan.name,
                kind=plan.kind, branch=plan.branch, selection=snap, status="queued",
                jenkins_job=name, build_number=build_number, jenkins_url=build_url,
                freshness=fresh, created_by=user.id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
