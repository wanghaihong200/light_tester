# tests/test_ui_plan10_models.py
from app.database import SessionLocal
from app.models import Project, UiAuthState, UiRun, UiScript


def test_plan10_columns_defaults_and_roundtrip():
    db = SessionLocal()
    try:
        p = Project(name="p10-m1")
        db.add(p); db.flush()
        s = UiScript(project_id=p.id, name="跨端", driver_target="android",
                     script={"version": 2, "meta": {"target": "android"}, "steps": []})
        db.add(s); db.flush()  # 强外键:先 flush 取 s.id 再建执行记录(同 test_ui_models.py 模式)
        r = UiRun(project_id=p.id, script_id=s.id, driver_target="harmony",
                  ai_usage={"input_tokens": 10, "output_tokens": 5, "report_path": "r.html"})
        a = UiAuthState(project_id=p.id, name="快照", storage_path="x.tar",
                        kind="android_snapshot", app_package="com.demo.app")
        db.add_all([s, r, a]); db.commit()
        assert s.driver_target == "android"
        assert r.ai_usage["output_tokens"] == 5
        assert a.kind == "android_snapshot" and a.app_package == "com.demo.app"
        # 缺省值:老路径语义不变
        s2 = UiScript(project_id=p.id, name="老Web", script={"version": 1, "steps": []})
        db.add(s2); db.flush()  # 强外键:先 flush 取 s2.id 再建执行记录
        r2 = UiRun(project_id=p.id, script_id=s2.id)
        a2 = UiAuthState(project_id=p.id, name="网页态", storage_path="y.json")
        db.add_all([s2, r2, a2]); db.commit()
        assert s2.driver_target == "web" and r2.driver_target == "web" and a2.kind == "web_storage"
        assert a2.app_package is None and r2.ai_usage is None
    finally:
        db.close()
