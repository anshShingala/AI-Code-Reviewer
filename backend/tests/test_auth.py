import uuid
from datetime import timedelta
from fastapi.testclient import TestClient
from app.core.security import create_access_token
from app.main import app

client = TestClient(app)
TEST_SECRET = "test-secret-key-12345"


def test_missing_authentication_rejected() -> None:
    """Unauthenticated request without Authorization header returns 401."""
    response = client.get("/api/v1/test-auth")
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_invalid_token_rejected() -> None:
    """Request with invalid/tampered token returns 401."""
    headers = {"Authorization": "Bearer invalid.token.value"}
    response = client.get("/api/v1/test-auth", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_expired_token_rejected() -> None:
    """Request with expired token returns 401."""
    user_id = str(uuid.uuid4())
    token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(seconds=-10),
        secret_key=TEST_SECRET,
    )
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get("/api/v1/test-auth", headers=headers)
    assert response.status_code == 401


def test_valid_token_authentication_success() -> None:
    """Valid token resolves authenticated user identity context."""
    user_id = str(uuid.uuid4())
    token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(minutes=15),
        secret_key=TEST_SECRET,
    )
    headers = {"Authorization": f"Bearer {token}"}

    # Override AUTH_SECRET for test duration
    from app.core import config
    original_secret = config.settings.AUTH_SECRET
    config.settings.AUTH_SECRET = TEST_SECRET
    try:
        response = client.get("/api/v1/test-auth", headers=headers)
        assert response.status_code == 200
        assert response.json() == {
            "status": "authenticated",
            "user_id": user_id,
        }
    finally:
        config.settings.AUTH_SECRET = original_secret


def test_spoofed_user_id_header_ignored() -> None:
    """Client-supplied X-User-ID header is ignored and unauthenticated request fails."""
    headers = {"X-User-ID": str(uuid.uuid4())}
    response = client.get("/api/v1/test-auth", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


def test_auth_failure_does_not_leak_secrets() -> None:
    """Authentication failures return clean 401 payload without internal secret leakage."""
    headers = {"Authorization": "Bearer bad-token"}
    response = client.get("/api/v1/test-auth", headers=headers)
    assert response.status_code == 401
    content = response.text
    assert TEST_SECRET not in content
    assert "Traceback" not in content
