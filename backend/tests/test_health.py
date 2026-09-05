from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok():
    with TestClient(create_app()) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
