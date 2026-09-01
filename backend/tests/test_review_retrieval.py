import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest
from cryptography.fernet import Fernet

from app.core import config
from app.core.security import create_access_token
from app.main import app
from app.api.reviews import _MOCK_REVIEWS_STORE

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


# 1 & 2. Authenticated & Unauthenticated Review Listing
def test_unauthenticated_review_listing_rejected() -> None:
    res = client.get("/api/v1/reviews")
    assert res.status_code == 401


def test_authenticated_review_listing_success(mock_github_sha) -> None:
    user_id = str(uuid.uuid4())
    headers = get_auth_header(user_id=user_id)

    # Create a review first
    create_headers = {**headers, "Idempotency-Key": str(uuid.uuid4())}
    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["app/main.py"],
        "categories": ["BUG"],
    }
    client.post("/api/v1/reviews", json=payload, headers=create_headers)

    res = client.get("/api/v1/reviews", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "limit" in data
    assert "offset" in data
    assert "reviews" in data
    assert data["total"] >= 1


# 3. User Isolation in Review Listing
def test_user_isolation_in_review_listing(mock_github_sha) -> None:
    user1_id = str(uuid.uuid4())
    user2_id = str(uuid.uuid4())

    headers1 = get_auth_header(user_id=user1_id)
    headers2 = get_auth_header(user_id=user2_id)

    # User 1 creates review
    client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["a.py"], "categories": ["BUG"]},
        headers={**headers1, "Idempotency-Key": str(uuid.uuid4())},
    )

    res1 = client.get("/api/v1/reviews", headers=headers1)
    res2 = client.get("/api/v1/reviews", headers=headers2)

    assert res1.status_code == 200
    assert res2.status_code == 200
    # User 2 sees 0 reviews created by User 1
    assert res2.json()["total"] == 0


# 4. Status Filtering
def test_status_filtering(mock_github_sha) -> None:
    user_id = str(uuid.uuid4())
    headers = get_auth_header(user_id=user_id)

    client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["a.py"], "categories": ["BUG"]},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )

    res = client.get("/api/v1/reviews?status=PROCESSING", headers=headers)
    assert res.status_code == 200
    for r in res.json()["reviews"]:
        assert r["status"] == "PROCESSING"


# 5 & 6. Limit and Offset Parameters
def test_limit_and_offset_parameters(mock_github_sha) -> None:
    headers = get_auth_header()
    res = client.get("/api/v1/reviews?limit=5&offset=0", headers=headers)
    assert res.status_code == 200
    assert res.json()["limit"] == 5
    assert res.json()["offset"] == 0


# 8. Review Detail Success
def test_review_detail_success(mock_github_sha) -> None:
    user_id = str(uuid.uuid4())
    headers = get_auth_header(user_id=user_id)
    idem_key = str(uuid.uuid4())

    create_res = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["app/main.py"], "categories": ["BUG"]},
        headers={**headers, "Idempotency-Key": idem_key},
    )
    assert create_res.status_code == 202
    review_id = create_res.json()["id"]

    res = client.get(f"/api/v1/reviews/{review_id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == review_id
    assert "status" in data
    assert "files" in data
    assert "findings_count" in data


# 9. Non-existent Review -> 404
def test_nonexistent_review_returns_404() -> None:
    headers = get_auth_header()
    fake_id = str(uuid.uuid4())
    res = client.get(f"/api/v1/reviews/{fake_id}", headers=headers)
    assert res.status_code == 404


# 10. Cross-User Review Detail -> 404 (IDOR Protection)
def test_cross_user_review_detail_returns_404(mock_github_sha) -> None:
    user1_headers = get_auth_header()
    user2_headers = get_auth_header()

    create_res = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["a.py"], "categories": ["BUG"]},
        headers={**user1_headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    review_id = create_res.json()["id"]

    # User 2 attempts to fetch User 1's review -> 404
    res = client.get(f"/api/v1/reviews/{review_id}", headers=user2_headers)
    assert res.status_code == 404


# 13. Findings Retrieval Success
def test_findings_retrieval_success(mock_github_sha) -> None:
    user_id = str(uuid.uuid4())
    headers = get_auth_header(user_id=user_id)

    create_res = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["app/main.py"], "categories": ["BUG"]},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    review_id = create_res.json()["id"]

    res = client.get(f"/api/v1/reviews/{review_id}/findings", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["review_id"] == review_id
    assert "total_findings" in data
    assert "findings" in data


# 14, 15, 16. Findings Filtering by File Path, Category, Severity
def test_findings_filtering_and_taxonomy_validation(mock_github_sha) -> None:
    user_id = str(uuid.uuid4())
    headers = get_auth_header(user_id=user_id)

    create_res = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["app/main.py"], "categories": ["BUG"]},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    review_id = create_res.json()["id"]

    # Add mock finding in store for test
    mock_key = (user_id, list(_MOCK_REVIEWS_STORE.keys())[-1][1])
    _MOCK_REVIEWS_STORE[mock_key]["findings"] = [
        {
            "id": str(uuid.uuid4()),
            "file_path": "app/main.py",
            "line_number": 10,
            "severity": "HIGH",
            "category": "SECURITY",
            "title": "Secret in code",
            "message": "Detail",
            "suggestion": "Fix",
            "created_at": "2026-09-01T00:00:00Z",
        }
    ]

    # Category filter
    res_cat = client.get(f"/api/v1/reviews/{review_id}/findings?category=SECURITY", headers=headers)
    assert res_cat.status_code == 200
    assert res_cat.json()["total_findings"] == 1

    # Severity filter
    res_sev = client.get(f"/api/v1/reviews/{review_id}/findings?severity=HIGH", headers=headers)
    assert res_sev.status_code == 200
    assert res_sev.json()["total_findings"] == 1

    # Invalid Category -> 400
    res_inv_cat = client.get(f"/api/v1/reviews/{review_id}/findings?category=INVALID", headers=headers)
    assert res_inv_cat.status_code == 400

    # Invalid Severity -> 400
    res_inv_sev = client.get(f"/api/v1/reviews/{review_id}/findings?severity=INVALID", headers=headers)
    assert res_inv_sev.status_code == 400


# 21. Cross-User Findings Review -> 404
def test_cross_user_findings_review_returns_404(mock_github_sha) -> None:
    user1_headers = get_auth_header()
    user2_headers = get_auth_header()

    create_res = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["a.py"], "categories": ["BUG"]},
        headers={**user1_headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    review_id = create_res.json()["id"]

    res = client.get(f"/api/v1/reviews/{review_id}/findings", headers=user2_headers)
    assert res.status_code == 404


# 22. Malformed UUID -> 400
def test_malformed_uuid_returns_400() -> None:
    headers = get_auth_header()
    res1 = client.get("/api/v1/reviews/not-a-uuid", headers=headers)
    assert res1.status_code == 400
    assert "Invalid review_id format" in res1.json()["detail"]

    res2 = client.get("/api/v1/reviews/not-a-uuid/findings", headers=headers)
    assert res2.status_code == 400
    assert "Invalid review_id format" in res2.json()["detail"]


# 24. Secret Fields Not Exposed
def test_secret_fields_not_exposed(mock_github_sha) -> None:
    user_id = str(uuid.uuid4())
    headers = get_auth_header(user_id=user_id)

    create_res = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["a.py"], "categories": ["BUG"]},
        headers={**headers, "Idempotency-Key": str(uuid.uuid4())},
    )
    review_id = create_res.json()["id"]

    res_detail = client.get(f"/api/v1/reviews/{review_id}", headers=headers)
    text = res_detail.text
    assert "access_token" not in text
    assert TEST_ENCRYPTION_KEY not in text
    assert TEST_AUTH_SECRET not in text
