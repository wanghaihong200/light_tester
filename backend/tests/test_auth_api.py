from app.bootstrap import ensure_bootstrap_admin
from app.auth import hash_password
from app.models import User


def _seed_admin(client, db_session):
    admin = ensure_bootstrap_admin(db_session)
    db_session.expire_all()
    return admin


def test_login_ok_and_me(client, db_session):
    _seed_admin(client, db_session)
    r = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["username"] == "admin" and body["token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert r.status_code == 200 and r.json()["is_admin"] is True


def test_login_wrong_password_401_uniform(client, db_session):
    _seed_admin(client, db_session)
    r = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401 and r.json()["detail"] == "用户名或密码错误"
    r = client.post("/api/auth/login", json={"username": "ghost", "password": "nope"})
    assert r.status_code == 401 and r.json()["detail"] == "用户名或密码错误"  # 同文案不泄露


def test_me_rejects_bad_token_and_disabled(client, db_session):
    _seed_admin(client, db_session)
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Bearer junk"}).status_code == 401
    tok = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"}).json()["token"]
    u = db_session.query(User).filter(User.username == "admin").first()
    u.is_active = False
    db_session.commit()
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
