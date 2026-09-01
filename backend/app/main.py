from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.github import router as github_router
from app.api.reviews import router as reviews_router
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models import User

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
