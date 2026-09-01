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

## Execution Ownership Leasing & Stale Review Reclamation (AM-002)
- **Ownership Acquisition**: `acquire_ownership()` atomically assigns a unique worker identity string (`owner_identity`) and expiration timestamp (`owner_expires_at`) to a `Review` in `PROCESSING` status.
- **Worker Fencing**: `verify_fencing()` verifies active lease ownership (`owner_expires_at >= now()` and matching `owner_identity`) prior to findings persistence, fencing out stale or zombie worker writes.
- **Stale Review Reclamation**: `reclaim_stale_reviews()` queries abandoned reviews (`status == 'PROCESSING'` and `owner_expires_at < now()`) and transitions them to `FAILED` with explicit error message `Review processing timed out or worker crash detected (AM-002 execution lease expired)`.
- **Zero Schema Cost**: Operates entirely within the pre-built `owner_identity` and `owner_expires_at` columns of the frozen 5-table schema (`ix_reviews_owner_expires`).

## Execution Recovery & Maintenance Reclamation Service (AM-003 / Prompt 14)
- **Maintenance Endpoint**: `POST /api/v1/maintenance/reclaim-stale-reviews` triggers on-demand or periodic execution recovery reclamation.
- **Authenticated Access**: Requires valid JWT token authentication (`get_current_user`), guarding against unauthorized trigger calls.
- **Response Payload**: Returns structured summary (`status: "success"`, `reclaimed_count`, `reclaimed_review_ids`) with zero secret leakage.
- **Active Lease Protection**: Guarantees active processing reviews with unexpired leases (`owner_expires_at >= now()`) remain untouched.

## Asynchronous Background Execution Dispatcher (AM-004 / Prompt 15)
- **Background Dispatcher**: `POST /api/v1/reviews` uses FastAPI's native `BackgroundTasks` to queue `execute_review_engine` asynchronously upon new review creation.
- **Session-Isolated Background Execution**: `_run_review_engine_background()` obtains a dedicated independent DB session (`SessionLocal()`) enclosed in a `try...finally: db.close()` block, preventing closed-session errors or connection leaks after the HTTP response returns.
- **Strict AM-001 Replay Coexistence**: Background processing tasks are dispatched **ONLY** for new review creations (Case 3). Idempotent request replays (Case 1) return `202 Accepted` immediately without enqueuing duplicate background execution tasks.
- **Zero Queue Infrastructure**: Operates entirely within native FastAPI without Redis, Celery, RabbitMQ, Kafka, or external messaging dependencies.

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

## Frontend Next.js Architecture (Prompts 09 & 10)
- **Framework & Router**: Next.js 14 App Router with React 18, TypeScript, Tailwind CSS, and Lucide React icons.
- **Client API Layer**: `src/lib/api.ts` provides strongly typed wrapper around backend REST endpoints (`/api/v1`) with automatic Bearer token injection and HTTP 401 token cleanup.
- **Component Architecture**:
  - `GitHubConnect`: Handles OAuth authorization trigger and GitHub connection status indicator.
  - `RepoSelector`: Multi-stage dropdown cascade for repository selection, branch discovery, and recursive Git tree traversal.
  - `ReviewForm`: Configures categories, generates client-side UUID `Idempotency-Key` headers, and submits reviews to `POST /api/v1/reviews`.
  - `ReviewHistory`: Renders paginated historical reviews with status badges (`PROCESSING`, `COMPLETED`, `FAILED`) and live polling/refresh.
  - `FindingsDashboard`: Displays detailed review summary, error banner, and findings list with multi-faceted filtering (file path, category, severity).

## End-to-End System Integration & Verification (Prompt 11)
- **Full-Stack Alignment**: Seamless communication between Next.js frontend (`http://127.0.0.1:3000`) and FastAPI backend (`http://127.0.0.1:8000`).
- **Verification Integrity**: Passed 74 backend pytest unit and integration tests (`tests/`) and zero-error Next.js production build (`npm run build`).
- **Contract Enforcement**: Enforces zero-regression against all frozen specifications across Prompts 01–10.

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
