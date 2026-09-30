# ─── Health endpoint ─────────────────────────────────────────
# Uses TestClient WITHOUT a context manager, so the application
# lifespan (which creates database tables and therefore requires a
# live PostgreSQL) never runs — the health route has no DB dependency.
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health_returns_active():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["system"] == "PMAS Cloud Core"
