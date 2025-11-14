from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_and_openapi():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    r2 = client.get("/openapi.yaml")
    assert r2.status_code == 200
    assert "openapi" in r2.text or r2.headers.get("content-type")
