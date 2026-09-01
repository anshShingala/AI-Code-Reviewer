from typing import Any
from fastapi import HTTPException, status
import httpx
from app.core.config import settings

GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"


class GitHubService:
    """Service handling server-side interactions with GitHub REST API."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=10.0)

    def _handle_http_error(self, response: httpx.Response) -> None:
        """Translate upstream GitHub HTTP errors into clean application HTTP exceptions."""
        if response.is_success:
            return

        status_code = response.status_code
        if status_code == 401:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="GitHub authentication failed or access token revoked.",
            )
        elif status_code in (403, 429):
            headers = {}
            retry_after = response.headers.get("Retry-After") or response.headers.get("X-RateLimit-Reset")
            if retry_after:
                headers["Retry-After"] = str(retry_after)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="GitHub API rate limit exceeded.",
                headers=headers if headers else None,
            )
        elif status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requested GitHub repository or resource not found.",
            )
        elif status_code >= 500:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Upstream GitHub service error.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"GitHub API error ({status_code}).",
            )

    def exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchange OAuth authorization code for GitHub access token."""
        if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub client credentials not configured.",
            )

        payload = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
        }
        if settings.GITHUB_REDIRECT_URI:
            payload["redirect_uri"] = settings.GITHUB_REDIRECT_URI

        headers = {"Accept": "application/json"}
        try:
            res = self.client.post(GITHUB_OAUTH_TOKEN_URL, json=payload, headers=headers)
            self._handle_http_error(res)
            data = res.json()
            if "error" in data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"GitHub OAuth error: {data.get('error_description', data['error'])}",
                )
            return data
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub OAuth exchange timed out.",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to GitHub OAuth endpoint.",
            )

    def get_authenticated_github_user(self, access_token: str) -> dict[str, Any]:
        """Retrieve authenticated GitHub user profile data."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            res = self.client.get(f"{GITHUB_API_BASE}/user", headers=headers)
            self._handle_http_error(res)
            return res.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub API timed out.",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to GitHub API.",
            )

    def get_user_repositories(self, access_token: str) -> list[dict[str, Any]]:
        """Retrieve repositories accessible by authenticated GitHub token."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        params = {"sort": "updated", "per_page": 100}
        try:
            res = self.client.get(f"{GITHUB_API_BASE}/user/repos", headers=headers, params=params)
            self._handle_http_error(res)
            return res.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub API timed out.",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to GitHub API.",
            )

    def get_repository_branches(
        self, access_token: str, owner: str, repo: str
    ) -> list[dict[str, Any]]:
        """Retrieve branches for a target repository."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            res = self.client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/branches", headers=headers)
            self._handle_http_error(res)
            return res.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub API timed out.",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to GitHub API.",
            )

    def resolve_ref_to_sha(
        self, access_token: str, owner: str, repo: str, ref: str
    ) -> str:
        """Resolve a branch/ref name to an exact 40-character commit SHA."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        try:
            res = self.client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{ref}", headers=headers)
            self._handle_http_error(res)
            data = res.json()
            sha: str = data.get("sha", "")
            if not sha:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Could not resolve ref '{ref}' to commit SHA.",
                )
            return sha
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub API timed out.",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to GitHub API.",
            )

    def get_git_tree(
        self, access_token: str, owner: str, repo: str, sha_or_ref: str
    ) -> dict[str, Any]:
        """Retrieve recursive Git Tree for a specific commit SHA or ref."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        params = {"recursive": "1"}
        try:
            res = self.client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{sha_or_ref}",
                headers=headers,
                params=params,
            )
            self._handle_http_error(res)
            return res.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub API timed out.",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to GitHub API.",
            )

    def get_file_content(
        self, access_token: str, owner: str, repo: str, path: str, sha: str
    ) -> dict[str, Any]:
        """Retrieve raw file content object for a specific path and commit SHA."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        }
        params = {"ref": sha}
        try:
            res = self.client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}",
                headers=headers,
                params=params,
            )
            self._handle_http_error(res)
            return res.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="GitHub API timed out.",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to connect to GitHub API.",
            )
