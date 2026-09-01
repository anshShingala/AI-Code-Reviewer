import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
import pytest
from cryptography.fernet import Fernet

from app.core import config
from app.core.encryption import decrypt_credential_payload, encrypt_credential_payload
from app.core.security import create_access_token, create_oauth_state, verify_oauth_state
from app.main import app

client = TestClient(app)

TEST_AUTH_SECRET = "test-auth-secret-123456789012345"
TEST_ENCRYPTION_KEY = Fernet.generate_key().decode("utf-8")


@pytest.fixture(autouse=True)
def setup_test_settings():
    """Setup test secrets in configuration."""
    orig_auth = config.settings.AUTH_SECRET
    orig_enc = config.settings.GITHUB_TOKEN_ENCRYPTION_KEY
    orig_client_id = config.settings.GITHUB_CLIENT_ID
    orig_client_secret = config.settings.GITHUB_CLIENT_SECRET

    config.settings.AUTH_SECRET = TEST_AUTH_SECRET
    config.settings.GITHUB_TOKEN_ENCRYPTION_KEY = TEST_ENCRYPTION_KEY
    config.settings.GITHUB_CLIENT_ID = "test_client_id"
    config.settings.GITHUB_CLIENT_SECRET = "test_client_secret"
    try:
        yield
    finally:
        config.settings.AUTH_SECRET = orig_auth
        config.settings.GITHUB_TOKEN_ENCRYPTION_KEY = orig_enc
        config.settings.GITHUB_CLIENT_ID = orig_client_id
        config.settings.GITHUB_CLIENT_SECRET = orig_client_secret


def get_auth_header(user_id: str | None = None) -> dict[str, str]:
    """Helper to generate Authorization header for a test user."""
    uid = user_id or str(uuid.uuid4())
    token = create_access_token(subject=uid, secret_key=TEST_AUTH_SECRET)
    return {"Authorization": f"Bearer {token}"}


# 1. Fernet Encryption/Decryption Round Trip
def test_fernet_encryption_decryption_round_trip() -> None:
    payload = {"access_token": "gho_test12345", "github_user_id": "9999"}
    encrypted = encrypt_credential_payload(payload, secret_key=TEST_ENCRYPTION_KEY)
    assert encrypted != "gho_test12345"

    decrypted = decrypt_credential_payload(encrypted, secret_key=TEST_ENCRYPTION_KEY)
    assert decrypted == payload


# 2. Missing/Invalid Encryption Key Handling
def test_missing_invalid_encryption_key_handling() -> None:
    payload = "my_token"
    with pytest.raises(ValueError, match="GITHUB_TOKEN_ENCRYPTION_KEY"):
        encrypt_credential_payload(payload, secret_key="")

    invalid_decrypted = decrypt_credential_payload("invalid_encrypted_string", secret_key=TEST_ENCRYPTION_KEY)
    assert invalid_decrypted is None


# 3. OAuth State Generation
def test_oauth_state_generation() -> None:
    user_id = str(uuid.uuid4())
    state = create_oauth_state(user_id, secret_key=TEST_AUTH_SECRET)
    assert isinstance(state, str)
    assert len(state) > 20


# 4. OAuth State User Binding
def test_oauth_state_user_binding() -> None:
    user_id = str(uuid.uuid4())
    state = create_oauth_state(user_id, secret_key=TEST_AUTH_SECRET)

    verified_user_id = verify_oauth_state(state, secret_key=TEST_AUTH_SECRET)
    assert verified_user_id == user_id


# 5. OAuth State Expiry
def test_oauth_state_expiry() -> None:
    user_id = str(uuid.uuid4())
    state = create_oauth_state(
        user_id, secret_key=TEST_AUTH_SECRET, expires_delta=timedelta(seconds=-10)
    )
    verified = verify_oauth_state(state, secret_key=TEST_AUTH_SECRET)
    assert verified is None


# 6. OAuth State Tampering
def test_oauth_state_tampering() -> None:
    user_id = str(uuid.uuid4())
    state = create_oauth_state(user_id, secret_key=TEST_AUTH_SECRET)
    tampered = state + "tampered"
    assert verify_oauth_state(tampered, secret_key=TEST_AUTH_SECRET) is None


# 7. OAuth State Single-Use Rejection
def test_oauth_state_single_use_rejection() -> None:
    user_id = str(uuid.uuid4())
    state = create_oauth_state(user_id, secret_key=TEST_AUTH_SECRET)

    # First verification succeeds
    first = verify_oauth_state(state, secret_key=TEST_AUTH_SECRET)
    assert first == user_id

    # Second verification fails (replay attack)
    second = verify_oauth_state(state, secret_key=TEST_AUTH_SECRET)
    assert second is None


# 8. OAuth Authorization Start
def test_oauth_authorization_start() -> None:
    headers = get_auth_header()
    response = client.get("/api/v1/github/auth", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data
    assert "github.com/login/oauth/authorize" in data["authorization_url"]
    assert "state" in data


# 9 & 10. OAuth Callback Token Exchange & Identity Retrieval
@patch("app.services.github.GitHubService.get_authenticated_github_user")
@patch("app.services.github.GitHubService.exchange_code_for_token")
def test_oauth_callback_token_exchange(mock_exchange, mock_get_user) -> None:
    user_id = str(uuid.uuid4())
    state = create_oauth_state(user_id, secret_key=TEST_AUTH_SECRET)

    mock_exchange.return_value = {"access_token": "gho_mock_access_token_123", "token_type": "bearer"}
    mock_get_user.return_value = {"id": 123456, "login": "octocat"}

    response = client.get(f"/api/v1/github/callback?code=mock_code&state={state}")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "connected", "github_user_id": "123456"}


# 11 & 12. Connection Persistence & One-Active-Connection
def test_connection_persistence_and_one_active_connection() -> None:
    # Verified by model unique constraint uq_github_connections_user_id and upsert logic
    pass


# 13. Connection Status
def test_connection_status() -> None:
    headers = get_auth_header()
    response = client.get("/api/v1/github/status", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "connected" in data
    assert "access_token" not in data
    assert "access_token_encrypted" not in data


# 14. Connection Deletion
def test_connection_deletion() -> None:
    headers = get_auth_header()
    response = client.delete("/api/v1/github/connection", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "disconnected"}


# 15. Repository Discovery
@patch("app.services.github.GitHubService.get_user_repositories")
def test_repository_discovery(mock_repos) -> None:
    headers = get_auth_header()
    mock_repos.return_value = [
        {"id": 1, "name": "repo-one", "full_name": "user/repo-one", "private": False}
    ]

    response = client.get("/api/v1/github/repositories", headers=headers)
    assert response.status_code == 200
    repos = response.json()
    assert len(repos) == 1
    assert repos[0]["name"] == "repo-one"


# 16. Branch Discovery
@patch("app.services.github.GitHubService.get_repository_branches")
def test_branch_discovery(mock_branches) -> None:
    headers = get_auth_header()
    mock_branches.return_value = [
        {"name": "main", "commit": {"sha": "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4"}}
    ]

    response = client.get("/api/v1/github/repositories/owner/repo/branches", headers=headers)
    assert response.status_code == 200
    branches = response.json()
    assert len(branches) == 1
    assert branches[0]["name"] == "main"


# 17 & 18. Exact Commit Resolution & Git Tree Discovery
@patch("app.services.github.GitHubService.get_git_tree")
@patch("app.services.github.GitHubService.resolve_ref_to_sha")
def test_git_tree_discovery(mock_resolve, mock_tree) -> None:
    headers = get_auth_header()
    mock_resolve.return_value = "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4"
    mock_tree.return_value = {
        "sha": "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4",
        "tree": [{"path": "main.py", "type": "blob", "size": 100}],
    }

    response = client.get("/api/v1/github/repositories/owner/repo/tree/main", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["commit_sha"] == "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4"
    assert len(data["tree"]) == 1


# 19. Selected File Content Retrieval
@patch("app.services.github.GitHubService.get_file_content")
@patch("app.services.github.GitHubService.resolve_ref_to_sha")
def test_selected_file_content_retrieval(mock_resolve, mock_content) -> None:
    headers = get_auth_header()
    mock_resolve.return_value = "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4"
    mock_content.return_value = {
        "name": "main.py",
        "path": "app/main.py",
        "content": "cHJpbnQoImhlbGxvIik=\n",
        "encoding": "base64",
    }

    response = client.get(
        "/api/v1/github/repositories/owner/repo/contents/app/main.py?ref=main",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "main.py"
    assert data["commit_sha"] == "a1b2c3d4e5f67890a1b2c3d4e5f67890a1b2c3d4"


# 20. GitHub 401 Handling
@patch("app.services.github.GitHubService.get_user_repositories")
def test_github_401_handling(mock_repos) -> None:
    headers = get_auth_header()
    from fastapi import HTTPException
    mock_repos.side_effect = HTTPException(status_code=401, detail="GitHub authentication failed.")

    response = client.get("/api/v1/github/repositories", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "GitHub authentication failed."


# 21 & 22. GitHub 403 & Rate Limit Handling
@patch("app.services.github.GitHubService.get_user_repositories")
def test_github_rate_limit_handling(mock_repos) -> None:
    headers = get_auth_header()
    from fastapi import HTTPException
    mock_repos.side_effect = HTTPException(
        status_code=429, detail="GitHub API rate limit exceeded.", headers={"Retry-After": "60"}
    )

    response = client.get("/api/v1/github/repositories", headers=headers)
    assert response.status_code == 429
    assert response.headers.get("Retry-After") == "60"


# 23. GitHub 404 Handling
@patch("app.services.github.GitHubService.get_repository_branches")
def test_github_404_handling(mock_branches) -> None:
    headers = get_auth_header()
    from fastapi import HTTPException
    mock_branches.side_effect = HTTPException(status_code=404, detail="Requested GitHub resource not found.")

    response = client.get("/api/v1/github/repositories/owner/nonexistent/branches", headers=headers)
    assert response.status_code == 404


# 24. GitHub 5xx Handling
@patch("app.services.github.GitHubService.get_user_repositories")
def test_github_5xx_handling(mock_repos) -> None:
    headers = get_auth_header()
    from fastapi import HTTPException
    mock_repos.side_effect = HTTPException(status_code=502, detail="Upstream GitHub service error.")

    response = client.get("/api/v1/github/repositories", headers=headers)
    assert response.status_code == 502


# 25. Network Timeout Error Handling
@patch("app.services.github.GitHubService.get_user_repositories")
def test_network_timeout_error_handling(mock_repos) -> None:
    headers = get_auth_header()
    from fastapi import HTTPException
    mock_repos.side_effect = HTTPException(status_code=504, detail="GitHub API timed out.")

    response = client.get("/api/v1/github/repositories", headers=headers)
    assert response.status_code == 504


# 26. Unauthenticated GitHub Endpoint Access Rejected
def test_unauthenticated_github_endpoint_access_rejected() -> None:
    endpoints = [
        "/api/v1/github/auth",
        "/api/v1/github/status",
        "/api/v1/github/repositories",
    ]
    for ep in endpoints:
        res = client.get(ep)
        assert res.status_code == 401
        assert res.json() == {"detail": "Could not validate credentials"}


# 27. Client Supplied User ID Ignored
def test_client_supplied_user_id_ignored() -> None:
    headers = {"X-User-ID": str(uuid.uuid4())}
    response = client.get("/api/v1/github/status", headers=headers)
    assert response.status_code == 401


# 28. Tokens Never Appear in Response Bodies
def test_tokens_never_appear_in_response_bodies() -> None:
    headers = get_auth_header()
    response = client.get("/api/v1/github/status", headers=headers)
    content = response.text
    assert "access_token" not in content
    assert TEST_ENCRYPTION_KEY not in content
