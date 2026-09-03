from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    """Verify application imports and foundation health endpoint responds correctly."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_favicon() -> None:
    """Verify GET /favicon.ico returns HTTP 204 No Content."""
    response = client.get("/favicon.ico")
    assert response.status_code == 204
