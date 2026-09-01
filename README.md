# AI Code Reviewer

## Project Purpose
AI Code Reviewer is an automated AI-driven code review platform designed to perform intelligent code reviews on GitHub Pull Requests using FastAPI, Next.js, and Google Gemini AI.

## Architecture Baseline
The project is structured as a single repository with logical separation:

```text
ai-code-reviewer/
├── backend/     # FastAPI backend service
│   ├── alembic/
│   ├── app/
│   │   ├── api/
│   │   │   └── deps.py      # Authentication dependency (get_current_user)
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── security.py  # JWT encoding & verification
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── models.py
│   │   │   └── session.py
│   │   └── main.py
│   ├── tests/
│   │   ├── test_auth.py
│   │   ├── test_main.py
│   │   └── test_models.py
│   ├── alembic.ini
│   └── requirements.txt
├── frontend/    # Next.js frontend application
├── tests/       # Test suites
├── docs/        # Documentation
└── .github/     # GitHub Actions workflows & templates
```

## Verified Runtime & Toolchain Baseline
- **Node.js**: `v22.19.0` (LTS)
- **Frontend Package Manager**: `npm` (`v11.16.0`)
- **Python Runtime**: `Python 3.12.3`
- **Python Dependency Tooling**: `venv` / `pip` (`v25.3`)
- **Backend Framework**: FastAPI `0.110.0`
- **Authentication**: `PyJWT 2.8.0` (HTTP Bearer token validation)
- **ORM & Persistence**: SQLAlchemy `2.0.28`
- **PostgreSQL Driver**: `psycopg2-binary 2.9.9` (Single PostgreSQL driver)
- **Migration System**: Alembic `1.13.1`
- **ASGI Server**: Uvicorn `0.28.0`
- **Testing Framework**: Pytest `8.1.1`
- **Version Control**: `Git 2.45.1`

## GitHub Integration Boundary
- **Fernet Token Encryption**: GitHub access tokens are encrypted with `cryptography 42.0.5` using `GITHUB_TOKEN_ENCRYPTION_KEY`. Tokens are never stored in plaintext and never exposed in API responses or logs.
- **Cryptographic OAuth State**: `GET /api/v1/github/auth` generates signed, user-bound, 10-minute expiring single-use OAuth state tokens.
- **Connection Persistence**: `GET /api/v1/github/callback` exchanges codes server-side, encrypts token payloads, and upserts `github_connections` enforcing 1-active-connection per user (`uq_github_connections_user_id`).
- **Protected GitHub Discovery Endpoints**:
  - `GET /api/v1/github/status`: Connection status metadata (zero tokens exposed).
  - `DELETE /api/v1/github/connection`: Disconnects user GitHub account (preserves historical review records).
  - `GET /api/v1/github/repositories`: List user's accessible GitHub repositories.
  - `GET /api/v1/github/repositories/{owner}/{repo}/branches`: List repository branches.
  - `GET /api/v1/github/repositories/{owner}/{repo}/tree/{ref}`: Recursive Git tree traversal.
  - `GET /api/v1/github/repositories/{owner}/{repo}/contents/{path}`: Source file content retrieval for exact resolved commit SHAs.

## Review Creation & Request Idempotency (AM-001)
- **Endpoint**: `POST /api/v1/reviews`
- **Mandatory Header**: `Idempotency-Key: <key-string>`
- **Logical Request Identity**: `authenticated_user` + `Idempotency-Key` header.
- **Canonical Payload Hash**: SHA-256 hex digest of sorted `repository_id`, `ref`, `files`, and uppercase taxonomy `categories` (`BUG`, `SECURITY`, `PERFORMANCE`, `MAINTAINABILITY`).
- **Replay Behavior**: Replaying identical `Idempotency-Key` + identical payload returns HTTP `202 Accepted` with the original Review object.
- **Conflict Behavior**: Reusing `Idempotency-Key` with a different payload returns HTTP `409 Conflict`.
- **Atomic Creation**: Review state created atomically inside a single PostgreSQL transaction. Concurrent race conditions on `uq_reviews_user_idempotency` are caught and resolved cleanly to existing review.

## AI Review Engine (Prompt 07)
- **AI Provider**: Google Gemini AI (`google-generativeai==0.4.1`) configured via `GEMINI_API_KEY` and `GEMINI_MODEL`. Zero hardcoded secrets.
- **The One-Gemini-Call Invariant**: Exactly 1 structured JSON model call per Review. No LLM self-correction passes, second-pass calls, or fallback LLM providers.
- **Deterministic Preflight**: Verifies GitHub token decryption, repository access, commit SHA resolution, and non-empty text file contents before invoking Gemini.
- **Prompt Injection Defense**: Encloses source code in `<SOURCE_CODE_TO_REVIEW>` boundary tags with instructions to treat comments, docstrings, and literals strictly as inert data to audit.
- **Post-Inference Validation**: Filters hallucinated file paths or line numbers out of range without calling Gemini again. Enforces taxonomy (`BUG`, `SECURITY`, `PERFORMANCE`, `MAINTAINABILITY`) and severities (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).
- **Deduplication & Persistence**: Deduplicates findings via tuple `(file_path, line_number, category, title)` and persists validated findings to the frozen `findings` table while updating `Review.status` to `COMPLETED` or `FAILED`.

## Review Retrieval & Findings Query API (Prompt 08)
- **Review History**: `GET /api/v1/reviews` returns paginated list of authenticated user's reviews sorted by `created_at DESC` with query filters (`status`, `limit`, `offset`).
- **Review Detail**: `GET /api/v1/reviews/{review_id}` returns detailed review metadata, file status list, and findings count. Non-existent or cross-user reviews return `404 Not Found` (IDOR defense).
- **Findings Query**: `GET /api/v1/reviews/{review_id}/findings` returns validated findings list with optional filtering by `file_path`, `category` (`BUG`, `SECURITY`, `PERFORMANCE`, `MAINTAINABILITY`), and `severity` (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`).

## Setup Instructions

### Backend Environment Setup
Create and activate the backend-local virtual environment:

```bash
cd backend
python -m venv .venv
```

Activation:
- **Windows (PowerShell)**: `.\.venv\Scripts\Activate.ps1`
- **macOS / Linux**: `source .venv/bin/activate`

Install dependencies:
```bash
pip install -r requirements.txt
```

### Environment Configuration
Configure environment variables via shell or secret manager (without committing credentials):
```bash
$env:DATABASE_URL="postgresql://<user>:<password>@localhost:5432/<dbname>"
$env:AUTH_SECRET="<your-secure-auth-secret>"
```

### Running Backend Server & Tests
Start Uvicorn:
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Run pytest test suite:
```bash
pytest
```
