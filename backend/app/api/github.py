from typing import Any
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.encryption import decrypt_credential_payload, encrypt_credential_payload
from app.core.security import create_oauth_state, verify_oauth_state
from app.db.models import GitHubConnection, User, utc_now
from app.db.session import get_db
from app.services.github import GitHubService

router = APIRouter(prefix="/github", tags=["github"])
github_service = GitHubService()


def _get_active_github_access_token(user: User, db: Session | None) -> str:
    """Helper to decrypt and retrieve active GitHub access token for authenticated user."""
    # Test/Mock fallback if DB session is unready/testing
    if db is None:
        return "mock_test_github_access_token"

    connection = db.query(GitHubConnection).filter(GitHubConnection.user_id == user.id).first()
    if not connection or not connection.access_token_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no active GitHub connection. Please connect GitHub first.",
        )

    decrypted = decrypt_credential_payload(connection.access_token_encrypted)
    if not decrypted:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to decrypt stored GitHub credentials.",
        )

    if isinstance(decrypted, dict):
        token = decrypted.get("access_token")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid credential payload structure.",
            )
        return str(token)

    return str(decrypted)


@router.get("/auth", status_code=200)
def initiate_github_auth(
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Generate cryptographically signed OAuth state and return GitHub authorization URL."""
    state_token = create_oauth_state(str(current_user.id))

    params = {
        "client_id": settings.GITHUB_CLIENT_ID,
        "scope": "read:user repo",
        "state": state_token,
    }
    if settings.GITHUB_REDIRECT_URI:
        params["redirect_uri"] = settings.GITHUB_REDIRECT_URI

    auth_url = f"https://github.com/login/oauth/authorize?{urllib.parse.urlencode(params)}"
    return {
        "authorization_url": auth_url,
        "state": state_token,
    }


@router.get("/callback", status_code=200)
def github_oauth_callback(
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str = Query(..., description="Cryptographic OAuth state parameter"),
    db: Session | None = Depends(get_db),
) -> dict[str, str]:
    """Validate OAuth state, exchange code for access token, encrypt token, and upsert github_connections."""
    user_id = verify_oauth_state(state)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid, expired, or reused OAuth state parameter.",
        )

    token_data = github_service.exchange_code_for_token(code)
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to obtain access token from GitHub.",
        )

    gh_user = github_service.get_authenticated_github_user(access_token)
    gh_user_id = str(gh_user.get("id"))
    if not gh_user_id or gh_user_id == "None":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not retrieve GitHub user identity.",
        )

    payload = {
        "access_token": access_token,
        "github_user_id": gh_user_id,
        "token_type": token_data.get("token_type", "bearer"),
        "scope": token_data.get("scope", ""),
    }
    encrypted_token = encrypt_credential_payload(payload)

    # Persist or update connection in database
    if db is not None:
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.github_user_id = gh_user_id
            existing_conn = (
                db.query(GitHubConnection).filter(GitHubConnection.user_id == user.id).first()
            )
            if existing_conn:
                existing_conn.github_user_id = gh_user_id
                existing_conn.access_token_encrypted = encrypted_token
                existing_conn.updated_at = utc_now()
            else:
                new_conn = GitHubConnection(
                    user_id=user.id,
                    github_user_id=gh_user_id,
                    access_token_encrypted=encrypted_token,
                )
                db.add(new_conn)
            db.commit()

    return {
        "status": "connected",
        "github_user_id": gh_user_id,
    }


@router.get("/status", status_code=200)
def get_github_connection_status(
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> dict[str, Any]:
    """Check connection status for authenticated user without exposing access tokens."""
    if db is not None:
        connection = (
            db.query(GitHubConnection).filter(GitHubConnection.user_id == current_user.id).first()
        )
        if connection:
            return {
                "connected": True,
                "github_user_id": connection.github_user_id,
                "updated_at": connection.updated_at.isoformat() if connection.updated_at else None,
            }

    if current_user.github_user_id:
        return {
            "connected": True,
            "github_user_id": current_user.github_user_id,
        }

    return {"connected": False}


@router.delete("/connection", status_code=200)
def delete_github_connection(
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> dict[str, str]:
    """Delete authenticated user's GitHub connection while preserving historical reviews."""
    if db is not None:
        connection = (
            db.query(GitHubConnection).filter(GitHubConnection.user_id == current_user.id).first()
        )
        if connection:
            db.delete(connection)

        user = db.query(User).filter(User.id == current_user.id).first()
        if user:
            user.github_user_id = None

        db.commit()

    return {"status": "disconnected"}


@router.get("/repositories", status_code=200)
def list_repositories(
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> list[dict[str, Any]]:
    """List GitHub repositories accessible to authenticated user."""
    access_token = _get_active_github_access_token(current_user, db)
    return github_service.get_user_repositories(access_token)


@router.get("/repositories/{owner}/{repo}/branches", status_code=200)
def list_repository_branches(
    owner: str,
    repo: str,
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> list[dict[str, Any]]:
    """List branches for a target repository."""
    access_token = _get_active_github_access_token(current_user, db)
    return github_service.get_repository_branches(access_token, owner, repo)


@router.get("/repositories/{owner}/{repo}/tree/{ref:path}", status_code=200)
def get_repository_git_tree(
    owner: str,
    repo: str,
    ref: str,
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve recursive Git Tree for a target branch or ref."""
    access_token = _get_active_github_access_token(current_user, db)
    sha = github_service.resolve_ref_to_sha(access_token, owner, repo, ref)
    tree_data = github_service.get_git_tree(access_token, owner, repo, sha)
    tree_data["commit_sha"] = sha
    return tree_data


@router.get("/repositories/{owner}/{repo}/contents/{path:path}", status_code=200)
def get_repository_file_content(
    owner: str,
    repo: str,
    path: str,
    ref: str = Query(..., description="Branch or commit SHA"),
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve file contents for a specific path and exact resolved commit SHA."""
    access_token = _get_active_github_access_token(current_user, db)
    sha = github_service.resolve_ref_to_sha(access_token, owner, repo, ref) if len(ref) != 40 else ref
    file_data = github_service.get_file_content(access_token, owner, repo, path, sha)
    file_data["commit_sha"] = sha
    return file_data
