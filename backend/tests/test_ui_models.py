from app.models import Project, UiAuthState, UiRun, UiScript


def test_ui_tables_create_and_defaults(client):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        p = Project(name="ui-m1")
        db.add(p)
        db.flush()
        s = UiScript(project_id=p.id, name="登录脚本", script={"version": 1, "steps": []})
        db.add(s)
        db.flush()  # 强外键：先取 s.id 再建执行记录
        r = UiRun(project_id=p.id, script_id=s.id, mode="headless")
        a = UiAuthState(project_id=p.id, name="管理员登录态", storage_path="x.json")
        db.add_all([s, r, a])
        db.commit()
        assert s.id > 0 and s.script["version"] == 1
        assert r.status == "pending" and r.steps_total == 0
        assert s.is_deleted is False
    finally:
        db.close()
