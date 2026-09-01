import json
from unittest.mock import MagicMock, patch
import uuid
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core import config
from app.core.security import create_access_token, create_oauth_state
from app.main import app

client = TestClient(app)

TEST_AUTH_SECRET = "test-auth-secret-123456789012345"
TEST_ENCRYPTION_KEY = Fernet.generate_key().decode("utf-8")


@pytest.fixture(autouse=True)
def setup_test_settings():
    """Setup test secrets in configuration."""
    orig_auth = config.settings.AUTH_SECRET
    orig_enc = config.settings.GITHUB_TOKEN_ENCRYPTION_KEY

    config.settings.AUTH_SECRET = TEST_AUTH_SECRET
    config.settings.GITHUB_TOKEN_ENCRYPTION_KEY = TEST_ENCRYPTION_KEY
    try:
        yield
    finally:
        config.settings.AUTH_SECRET = orig_auth
        config.settings.GITHUB_TOKEN_ENCRYPTION_KEY = orig_enc


def get_auth_header(user_id: str | None = None) -> dict[str, str]:
    """Helper to generate Authorization header for a test user."""
    uid = user_id or str(uuid.uuid4())
    token = create_access_token(subject=uid, secret_key=TEST_AUTH_SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_github_sha():
    with patch("app.services.github.GitHubService.resolve_ref_to_sha") as mock_sha:
        mock_sha.return_value = "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4"
        yield mock_sha


# E2E Scenario 1: Complete End-to-End User Flow
def test_e2e_complete_user_workflow(mock_github_sha) -> None:
    user_id = str(uuid.uuid4())
    auth_headers = get_auth_header(user_id=user_id)

    # 1. Health Check
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "healthy"

    # 2. Test Auth Verification
    auth_ver_res = client.get("/api/v1/test-auth", headers=auth_headers)
    assert auth_ver_res.status_code == 200
    assert auth_ver_res.json()["user_id"] == user_id

    # 3. GitHub OAuth Initiation
    github_auth_res = client.get("/api/v1/github/auth", headers=auth_headers)
    assert github_auth_res.status_code == 200
    assert "authorization_url" in github_auth_res.json()
    assert "state" in github_auth_res.json()

    # 4. GitHub Connection Status (Initial)
    status_res1 = client.get("/api/v1/github/status", headers=auth_headers)
    assert status_res1.status_code == 200
    assert "connected" in status_res1.json()

    # 5. Create Review Request with AM-001 Idempotency Key
    idem_key = str(uuid.uuid4())
    review_headers = {**auth_headers, "Idempotency-Key": idem_key}
    review_payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py", "src/utils.py"],
        "categories": ["BUG", "SECURITY"],
    }

    create_res = client.post("/api/v1/reviews", json=review_payload, headers=review_headers)
    assert create_res.status_code == 202
    review_data = create_res.json()
    assert "id" in review_data
    assert review_data["idempotency_key"] == idem_key
    assert review_data["status"] == "PROCESSING"

    review_id = review_data["id"]

    # 6. Replay Same Review Request -> 202 Replay
    replay_res = client.post("/api/v1/reviews", json=review_payload, headers=review_headers)
    assert replay_res.status_code == 202
    assert replay_res.json()["id"] == review_id

    # 7. Reuse Same Key with Conflicting Payload -> 409 Conflict
    conflict_payload = {**review_payload, "categories": ["PERFORMANCE"]}
    conflict_res = client.post("/api/v1/reviews", json=conflict_payload, headers=review_headers)
    assert conflict_res.status_code == 409

    # 8. Query Review History
    history_res = client.get("/api/v1/reviews", headers=auth_headers)
    assert history_res.status_code == 200
    history_data = history_res.json()
    assert history_data["total"] >= 1

    # 9. Query Review Detail
    detail_res = client.get(f"/api/v1/reviews/{review_id}", headers=auth_headers)
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == review_id

    # 10. Query Review Findings
    findings_res = client.get(f"/api/v1/reviews/{review_id}/findings", headers=auth_headers)
    assert findings_res.status_code == 200
    assert findings_res.json()["review_id"] == review_id


# E2E Scenario 2: Security & IDOR Isolation Enforcement
def test_e2e_security_idor_isolation(mock_github_sha) -> None:
    user1_id = str(uuid.uuid4())
    user2_id = str(uuid.uuid4())

    user1_headers = get_auth_header(user_id=user1_id)
    user2_headers = get_auth_header(user_id=user2_id)

    # User 1 creates review
    create_res = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["a.py"], "categories": ["BUG"]},
        headers={**user1_headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert create_res.status_code == 202
    review1_id = create_res.json()["id"]

    # User 2 attempts to fetch User 1's review detail -> 404 Not Found
    detail_res = client.get(f"/api/v1/reviews/{review1_id}", headers=user2_headers)
    assert detail_res.status_code == 404

    # User 2 attempts to fetch User 1's review findings -> 404 Not Found
    findings_res = client.get(f"/api/v1/reviews/{review1_id}/findings", headers=user2_headers)
    assert findings_res.status_code == 404

    # User 2 review listing does NOT include User 1's reviews
    history_res = client.get("/api/v1/reviews", headers=user2_headers)
    assert history_res.status_code == 200
    user2_reviews = [r["id"] for r in history_res.json()["reviews"]]
    assert review1_id not in user2_reviews


# E2E Scenario 3: Secret Protection & Non-Leakage
def test_e2e_secret_non_leakage_audit(mock_github_sha) -> None:
    headers = {**get_auth_header(), "Idempotency-Key": str(uuid.uuid4())}
    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["a.py"],
        "categories": ["BUG"],
    }

    response = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert response.status_code == 202
    review_id = response.json()["id"]

    # Audit response texts for secret leakage
    detail_res = client.get(f"/api/v1/reviews/{review_id}", headers=headers)
    findings_res = client.get(f"/api/v1/reviews/{review_id}/findings", headers=headers)
    status_res = client.get("/api/v1/github/status", headers=headers)

    for res in [response, detail_res, findings_res, status_res]:
        content = res.text
        assert TEST_AUTH_SECRET not in content
        assert TEST_ENCRYPTION_KEY not in content
        assert "access_token" not in content


# E2E Scenario 4: AM-006 System Operational Health Metrics Endpoint
def test_e2e_system_operational_health_metrics() -> None:
    """Verify GET /api/v1/reviews/system/health returns operational metrics."""
    response = client.get("/api/v1/reviews/system/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "database" in data
    assert "processing_reviews_count" in data
    assert "stale_reviews_count" in data
    assert data["gemini_service"] == "ready"

