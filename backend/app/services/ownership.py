"""AM-002 Execution Ownership Leasing & Stale Review Reclamation Service."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import uuid

from sqlalchemy.orm import Session
from app.db.models import Review, utc_now

DEFAULT_LEASE_SECONDS = 300  # 5 minute execution lease
AM002_TIMEOUT_ERROR = "Review processing timed out or worker crash detected (AM-002 execution lease expired)"


def generate_worker_identity() -> str:
    """Generate a unique worker instance identity string."""
    return f"worker-{uuid.uuid4()}"


def _normalize_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Ensure datetime is UTC timezone aware."""
    if dt is None or not isinstance(dt, datetime):
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def acquire_ownership(
    db: Session,
    review_or_id: str | uuid.UUID | Review,
    worker_identity: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> Optional[Review]:
    """
    Atomically acquire or renew an execution ownership lease on a Review entity in PROCESSING status.
    Returns the Review object if acquired successfully, or None if the review does not exist,
    is not in PROCESSING status, or is currently leased by another active worker.
    """
    now = utc_now()
    if isinstance(review_or_id, Review) or hasattr(review_or_id, "status"):
        review = review_or_id
    else:
        review_uuid = uuid.UUID(str(review_or_id)) if isinstance(review_or_id, str) else review_or_id
        try:
            review = (
                db.query(Review)
                .filter(Review.id == review_uuid)
                .with_for_update()
                .first()
            )
        except Exception:
            review = db.query(Review).filter(Review.id == review_uuid).first()

    if not review or getattr(review, "status", None) != "PROCESSING":
        return None

    owner_id = getattr(review, "owner_identity", None)
    expires_at = _normalize_utc(getattr(review, "owner_expires_at", None))

    is_expired = expires_at is not None and expires_at < now
    is_unassigned = owner_id is None or not isinstance(owner_id, str)
    is_same_owner = isinstance(owner_id, str) and owner_id == worker_identity

    if is_unassigned or is_same_owner or is_expired:
        review.owner_identity = worker_identity
        review.owner_expires_at = now + timedelta(seconds=lease_seconds)
        review.updated_at = now
        try:
            db.commit()
            db.refresh(review)
            return review
        except Exception:
            db.rollback()
            return None

    return None


def verify_fencing(
    db: Session | None,
    review_or_id: str | uuid.UUID | Review,
    worker_identity: str,
) -> bool:
    """
    Verify that worker_identity holds an active, non-expired execution lease.
    Forces an authoritative database lookup/refresh from PostgreSQL.
    If database refresh or query fails, returns False immediately.
    """
    now = utc_now()
    review: Review | None = None

    if db is None:
        if isinstance(review_or_id, Review) or hasattr(review_or_id, "status"):
            review = review_or_id  # type: ignore
        else:
            return False
    else:
        is_obj = isinstance(review_or_id, Review) or (
            hasattr(review_or_id, "status") and hasattr(review_or_id, "owner_identity")
        )

        if is_obj:
            try:
                db.refresh(review_or_id)  # type: ignore
                review = review_or_id  # type: ignore
            except Exception:
                return False
        else:
            try:
                review_uuid = (
                    uuid.UUID(str(review_or_id))
                    if isinstance(review_or_id, str)
                    else review_or_id
                )
                review = db.query(Review).filter(Review.id == review_uuid).first()
            except Exception:
                return False

    if not review:
        return False

    if getattr(review, "status", None) != "PROCESSING":
        return False

    owner_id = getattr(review, "owner_identity", None)
    expires_at = _normalize_utc(getattr(review, "owner_expires_at", None))

    if not isinstance(owner_id, str) or owner_id != worker_identity:
        return False

    if expires_at is not None and expires_at < now:
        return False

    return True


def reclaim_stale_reviews(
    db: Session,
    max_age_seconds: int = 0,
) -> List[Review]:
    """
    Scan for stale reviews in PROCESSING status whose execution lease has expired (owner_expires_at < now)
    and transition them to FAILED status with the explicit AM-002 timeout error message.
    """
    now = utc_now()
    threshold = now - timedelta(seconds=max_age_seconds)

    try:
        query = db.query(Review).filter(
            Review.status == "PROCESSING",
            Review.owner_expires_at.isnot(None),
            Review.owner_expires_at < threshold,
        ).with_for_update(skiplocked=True)
        stale_reviews = query.all()
    except Exception:
        stale_reviews = (
            db.query(Review)
            .filter(
                Review.status == "PROCESSING",
                Review.owner_expires_at.isnot(None),
                Review.owner_expires_at < threshold,
            )
            .all()
        )

    reclaimed: List[Review] = []
    for review in stale_reviews:
        review.status = "FAILED"
        review.error_message = AM002_TIMEOUT_ERROR
        review.owner_identity = None
        review.owner_expires_at = None
        review.updated_at = now
        reclaimed.append(review)

    if reclaimed:
        try:
            db.commit()
            for r in reclaimed:
                db.refresh(r)
        except Exception:
            db.rollback()

    return reclaimed
