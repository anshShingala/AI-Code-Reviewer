import uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest
from cryptography.fernet import Fernet

from app.core import config
from app.core.security import create_access_token
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
    """Mock GitHub ref SHA resolution."""
    with patch("app.services.github.GitHubService.resolve_ref_to_sha") as mock_sha:
        mock_sha.return_value = "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4"
        yield mock_sha


# 1. Unauthenticated Request Rejected
def test_unauthenticated_post_reviews_rejected() -> None:
    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["BUG"],
    }
    headers = {"Idempotency-Key": "key-123"}
    response = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Could not validate credentials"}


# 2 & 3. Missing or Blank Idempotency-Key Rejected
def test_missing_or_blank_idempotency_key_rejected() -> None:
    headers = get_auth_header()
    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["BUG"],
    }

    # Missing header
    res1 = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert res1.status_code == 400
    assert "Idempotency-Key header is required" in res1.json()["detail"]

    # Blank header
    blank_headers = {**headers, "Idempotency-Key": "   "}
    res2 = client.post("/api/v1/reviews", json=payload, headers=blank_headers)
    assert res2.status_code == 400
    assert "Idempotency-Key header is required" in res2.json()["detail"]


# 4 & 5. Valid Creation Returns 202 Accepted with Review ID
def test_new_valid_review_creation_success(mock_github_sha) -> None:
    headers = {**get_auth_header(), "Idempotency-Key": str(uuid.uuid4())}
    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["app/main.py", "app/config.py"],
        "categories": ["BUG", "SECURITY"],
    }

    response = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["status"] == "PROCESSING"
    assert "idempotency_key" in data
    assert "request_hash" in data
    assert len(data["request_hash"]) == 64


# 6. Sequential Same-Key Same-Payload Replay Returns Same Review
def test_sequential_same_key_same_payload_replay(mock_github_sha) -> None:
    idem_key = str(uuid.uuid4())
    headers = {**get_auth_header(), "Idempotency-Key": idem_key}
    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["BUG"],
    }

    res1 = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert res1.status_code == 202
    review1 = res1.json()

    res2 = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert res2.status_code == 202
    review2 = res2.json()

    assert review1["id"] == review2["id"]
    assert review1["request_hash"] == review2["request_hash"]


# 7 & 8. Same-Key Different-Payload Returns 409 Conflict
def test_same_key_different_payload_conflict(mock_github_sha) -> None:
    idem_key = str(uuid.uuid4())
    headers = {**get_auth_header(), "Idempotency-Key": idem_key}

    payload1 = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["BUG"],
    }
    payload2 = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["SECURITY"],  # Conflicting category
    }

    res1 = client.post("/api/v1/reviews", json=payload1, headers=headers)
    assert res1.status_code == 202

    res2 = client.post("/api/v1/reviews", json=payload2, headers=headers)
    assert res2.status_code == 409
    assert "Idempotency key reuse with conflicting request payload" in res2.json()["detail"]


# 9. Same Key Different Users Isolated
def test_same_key_different_users_isolated(mock_github_sha) -> None:
    shared_idem_key = str(uuid.uuid4())
    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["BUG"],
    }

    headers_user1 = {**get_auth_header(), "Idempotency-Key": shared_idem_key}
    headers_user2 = {**get_auth_header(), "Idempotency-Key": shared_idem_key}

    res1 = client.post("/api/v1/reviews", json=payload, headers=headers_user1)
    res2 = client.post("/api/v1/reviews", json=payload, headers=headers_user2)

    assert res1.status_code == 202
    assert res2.status_code == 202
    # Independent reviews created
    assert res1.json()["id"] != res2.json()["id"]


# 10. Same User New Key Creates New Review
def test_same_user_new_key_creates_new_review(mock_github_sha) -> None:
    user_headers = get_auth_header()
    headers1 = {**user_headers, "Idempotency-Key": str(uuid.uuid4())}
    headers2 = {**user_headers, "Idempotency-Key": str(uuid.uuid4())}

    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["BUG"],
    }

    res1 = client.post("/api/v1/reviews", json=payload, headers=headers1)
    res2 = client.post("/api/v1/reviews", json=payload, headers=headers2)

    assert res1.status_code == 202
    assert res2.status_code == 202
    assert res1.json()["id"] != res2.json()["id"]


# 13 & 14. Client-Supplied user_id or source_revision Ignored
def test_client_supplied_user_id_and_source_revision_ignored(mock_github_sha) -> None:
    headers = {**get_auth_header(), "Idempotency-Key": str(uuid.uuid4()), "X-User-ID": str(uuid.uuid4())}
    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["BUG"],
        "user_id": str(uuid.uuid4()),  # Spoofed user_id in body
        "source_revision": "0000000000000000000000000000000000000000",
    }

    response = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert response.status_code == 202
    # Server SHA resolution was called
    mock_github_sha.assert_called_once()


# 16. Invalid Repository Format Rejected
def test_invalid_repository_format_rejected() -> None:
    headers = {**get_auth_header(), "Idempotency-Key": str(uuid.uuid4())}
    payload = {
        "repository_id": "invalid_no_slash",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["BUG"],
    }
    response = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert response.status_code == 400
    assert "Invalid repository_id format" in response.json()["detail"]


# 17 & 18. Empty Files or Categories List Rejected
def test_empty_files_or_categories_list_rejected() -> None:
    headers = {**get_auth_header(), "Idempotency-Key": str(uuid.uuid4())}

    # Empty files
    res1 = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": [], "categories": ["BUG"]},
        headers=headers,
    )
    assert res1.status_code == 400

    # Empty categories
    res2 = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["src/main.py"], "categories": []},
        headers=headers,
    )
    assert res2.status_code == 400


# 19 & 20. Taxonomy Validation & Case Insensitivity
def test_category_taxonomy_validation_and_normalization(mock_github_sha) -> None:
    headers = {**get_auth_header(), "Idempotency-Key": str(uuid.uuid4())}

    # Invalid category
    invalid_res = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["src/main.py"], "categories": ["INVALID_CAT"]},
        headers=headers,
    )
    assert invalid_res.status_code == 400
    assert "Invalid review category" in invalid_res.json()["detail"]

    # Lowercase valid category normalized
    valid_res = client.post(
        "/api/v1/reviews",
        json={"repository_id": "owner/repo", "ref": "main", "files": ["src/main.py"], "categories": ["bug", "security"]},
        headers=headers,
    )
    assert valid_res.status_code == 202


# 21. Canonical Hash File & Category Sorting
def test_canonical_hash_sorting(mock_github_sha) -> None:
    idem_key = str(uuid.uuid4())
    headers = {**get_auth_header(), "Idempotency-Key": idem_key}

    payload1 = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["b.py", "a.py"],
        "categories": ["SECURITY", "BUG"],
    }
    payload2 = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["a.py", "b.py"],
        "categories": ["BUG", "SECURITY"],
    }

    res1 = client.post("/api/v1/reviews", json=payload1, headers=headers)
    res2 = client.post("/api/v1/reviews", json=payload2, headers=headers)

    assert res1.status_code == 202
    assert res2.status_code == 202
    # Sorted order results in identical hash and replay match
    assert res1.json()["request_hash"] == res2.json()["request_hash"]


# 22. No GitHub Credential Leaked in Response
def test_no_github_credential_leaked_in_review_response(mock_github_sha) -> None:
    headers = {**get_auth_header(), "Idempotency-Key": str(uuid.uuid4())}
    payload = {
        "repository_id": "owner/repo",
        "ref": "main",
        "files": ["src/main.py"],
        "categories": ["BUG"],
    }

    response = client.post("/api/v1/reviews", json=payload, headers=headers)
    assert response.status_code == 202
    content = response.text
    assert "access_token" not in content
    assert TEST_ENCRYPTION_KEY not in content
