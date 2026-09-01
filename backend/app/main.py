from typing import Any
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.github import router as github_router
from app.api.reviews import router as reviews_router
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db

app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(github_router, prefix="/api/v1")
app.include_router(reviews_router, prefix="/api/v1")


@app.get("/health", status_code=200)
def health_check() -> dict[str, str]:
    """Minimal development foundation health endpoint."""
    return {"status": "healthy"}


@app.get("/api/v1/test-auth", status_code=200)
def test_auth_verification(
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Test-only verification endpoint for testing authentication dependency context."""
    return {
        "status": "authenticated",
        "user_id": str(current_user.id),
    }


@app.post("/api/v1/maintenance/reclaim-stale-reviews", status_code=200)
def maintenance_reclaim_stale_reviews(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Operational maintenance endpoint for triggering stale review execution reclamation."""
    from app.services.ownership import reclaim_stale_reviews

    if db is None:
        return {"status": "success", "reclaimed_count": 0, "reclaimed_review_ids": []}

    reclaimed = reclaim_stale_reviews(db)
    return {
        "status": "success",
        "reclaimed_count": len(reclaimed),
        "reclaimed_review_ids": [str(r.id) for r in reclaimed],
    }

