# tests/test_staging.py
from app.database import SessionLocal
from app.models import GenerationJob, Module, Project, StagedCase


def _admin_headers(client, db_session):
    """Task 7 补鉴权:bootstrap admin 登录,返回 Authorization 头(admin 直通所有项目)。
    原断言语义不变,仅补鉴权头。"""
    from app.bootstrap import ensure_bootstrap_admin

    ensure_bootstrap_admin(db_session)
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


def _seed_staged(db, status="completed"):
    p = Project(name="暂存项目")
    db.add(p)
    db.flush()
    m = Module(project_id=p.id, name="登录模块")
    db.add(m)
    db.flush()
    job = GenerationJob(project_id=p.id, document_id=None, target_module_id=m.id, status=status)
    db.add(job)
    db.flush()
    s1 = StagedCase(job_id=job.id, feature_point_name="账号登录", title="登录成功", priority="P0", steps=[{"action": "a1", "expected": "e1"}])
    s2 = StagedCase(job_id=job.id, feature_point_name="账号登录", title="密码错误", priority="P1", steps=[])
    s3 = StagedCase(job_id=job.id, feature_point_name="扫码登录", title="扫码成功", priority="P1", steps=[])
    db.add_all([s1, s2, s3])
    db.commit()
    return p, m, job, [s1, s2, s3]


def test_staging_group_and_accept(client, db_session):
    ah = _admin_headers(client, db_session)
    db = SessionLocal()
    p, m, job, staged = _seed_staged(db)
    pid, mid, jid = p.id, m.id, job.id
    db.close()

    grouped = client.get(f"/api/jobs/{jid}/staging", headers=ah).json()
    assert [g["feature_point_name"] for g in grouped["groups"]] == ["账号登录", "扫码登录"]
    assert len(grouped["groups"][0]["cases"]) == 2

    resp = client.post(f"/api/jobs/{jid}/staging/accept", json={"ids": [staged[0].id, staged[2].id]}, headers=ah)
    assert resp.status_code == 200
    assert resp.json()["accepted"] == 2

    tree = client.get(f"/api/projects/{pid}/tree", headers=ah).json()
    fps = {f["name"] for f in tree[0]["feature_points"]}
    assert fps == {"账号登录", "扫码登录"}
    acc = next(f for f in tree[0]["feature_points"] if f["name"] == "账号登录")
    assert len(acc["cases"]) == 1 and acc["cases"][0]["title"] == "登录成功"
    # 未勾选的 s2 仍在暂存
    left = client.get(f"/api/jobs/{jid}/staging", headers=ah).json()
    assert [c["id"] for g in left["groups"] for c in g["cases"]] == [staged[1].id]
    # 步骤已入库
    detail = client.get(f"/api/cases/{acc['cases'][0]['id']}", headers=ah).json()
    assert detail["steps"][0]["action"] == "a1"


def test_staging_reject_deletes(client, db_session):
    ah = _admin_headers(client, db_session)
    db = SessionLocal()
    _, _, job, staged = _seed_staged(db)
    jid, sid = job.id, staged[1].id
    db.close()
    assert client.delete(f"/api/staged/{sid}", headers=ah).status_code == 204
    left = client.get(f"/api/jobs/{jid}/staging", headers=ah).json()
    assert sid not in [c["id"] for g in left["groups"] for c in g["cases"]]


def test_staging_accept_validation(client, db_session):
    ah = _admin_headers(client, db_session)
    db = SessionLocal()
    _, _, job, staged = _seed_staged(db)
    jid = job.id
    db.close()
    # 重复 accept:同一 id 第二次已不存在 → 400
    assert client.post(f"/api/jobs/{jid}/staging/accept", json={"ids": [staged[0].id]}, headers=ah).status_code == 200
    assert client.post(f"/api/jobs/{jid}/staging/accept", json={"ids": [staged[0].id]}, headers=ah).status_code == 400
    # 夹带不属于该 job 的 id → 400
    assert client.post(f"/api/jobs/{jid}/staging/accept", json={"ids": [staged[1].id, 999999]}, headers=ah).status_code == 400


def test_staging_accept_requires_completed(client, db_session):
    ah = _admin_headers(client, db_session)
    db = SessionLocal()
    _, _, job, staged = _seed_staged(db, status="pending")
    jid = job.id
    db.close()
    assert client.post(f"/api/jobs/{jid}/staging/accept", json={"ids": [staged[0].id]}, headers=ah).status_code == 400
    assert client.get("/api/jobs/999999/staging", headers=ah).status_code == 404
    assert client.delete("/api/staged/999999", headers=ah).status_code == 404
