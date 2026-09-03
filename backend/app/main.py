import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.api.github import router as github_router
from app.api.reviews import router as reviews_router
from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models import User
from app.db.session import get_db, get_sessionmaker
from app.services.ownership import reclaim_stale_reviews

logger = logging.getLogger(__name__)


def _run_stale_reclamation_once() -> None:
    """Execute a single stale review reclamation cycle with isolated session lifecycle management."""
    session_factory = get_sessionmaker()
    if not session_factory:
        return
    db = session_factory()
    try:
        reclaim_stale_reviews(db)
    except Exception as exc:
        logger.warning(f"Stale review reclamation iteration warning: {exc}")
    finally:
        db.close()


async def _stale_reclamation_ticker_loop(interval_seconds: int) -> None:
    """In-process periodic background ticker loop executing stale review reclamation at configured interval."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            _run_stale_reclamation_once()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"Stale reclamation ticker loop warning: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI application lifespan ContextManager handling startup recovery and periodic ticker loop."""
    # 1. AM-003 Startup Recovery: Execute immediate stale review reclamation on boot
    try:
        _run_stale_reclamation_once()
    except Exception as exc:
        logger.warning(f"Startup stale review reclamation warning: {exc}")

    # 2. AM-003 Periodic Ticker: Spawn background asyncio task if interval > 0
    ticker_task = None
    interval = settings.STALE_RECLAMATION_INTERVAL_SECONDS
    if interval > 0:
        ticker_task = asyncio.create_task(_stale_reclamation_ticker_loop(interval))

    try:
        yield
    finally:
        # 3. Graceful Shutdown: Cancel ticker task cleanly on application shutdown
        if ticker_task and not ticker_task.done():
            ticker_task.cancel()
            try:
                await ticker_task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title=settings.APP_NAME,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
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


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Handle GET /favicon.ico without returning 404."""
    return Response(status_code=204)


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

