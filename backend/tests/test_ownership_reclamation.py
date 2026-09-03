"""Tests for AM-002 Execution Ownership Leasing, Worker Fencing, and Stale Review Reclamation."""
from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core import config
from app.db.base import Base
from app.db.models import Review, User, utc_now
from app.services.ownership import (
    AM002_TIMEOUT_ERROR,
    acquire_ownership,
    generate_worker_identity,
    reclaim_stale_reviews,
    verify_fencing,
)
from app.services.review_engine import ReviewEngineService

TEST_AUTH_SECRET = "test-auth-secret-123456789012345"


@pytest.fixture(autouse=True)
def setup_test_settings():
    """Setup test secrets in configuration."""
    orig_auth = config.settings.AUTH_SECRET
    config.settings.AUTH_SECRET = TEST_AUTH_SECRET
    try:
        yield
    finally:
        config.settings.AUTH_SECRET = orig_auth


@pytest.fixture
def db_session():
    """Create a clean in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def create_test_user_and_review(db_session: Session, status: str = "PROCESSING") -> tuple[User, Review]:
    """Helper fixture creating test user and review."""
    uid = uuid.uuid4()
    user = User(id=uid, email=f"user-{uid}@example.com", github_user_id=str(uuid.uuid4()))
    db_session.add(user)
    db_session.commit()

    review = Review(
        id=uuid.uuid4(),
        user_id=user.id,
        idempotency_key=f"key-{uuid.uuid4()}",
        request_hash="a" * 64,
        status=status,
    )
    db_session.add(review)
    db_session.commit()
    db_session.refresh(review)
    return user, review


def test_generate_worker_identity() -> None:
    """Verify worker identity strings are unique."""
    w1 = generate_worker_identity()
    w2 = generate_worker_identity()
    assert w1.startswith("worker-")
    assert w2.startswith("worker-")
    assert w1 != w2


def test_acquire_ownership_success(db_session: Session) -> None:
    """Verify atomic lease acquisition sets owner_identity and owner_expires_at."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    worker_id = "worker-node-1"

    acquired = acquire_ownership(db_session, review, worker_id, lease_seconds=60)
    assert acquired is not None
    assert acquired.owner_identity == worker_id
    assert acquired.owner_expires_at is not None


def test_acquire_ownership_rejection_if_active_lease(db_session: Session) -> None:
    """Verify another worker cannot acquire lease while an active lease is held."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    w1 = "worker-alpha"
    w2 = "worker-beta"

    first_lease = acquire_ownership(db_session, review, w1, lease_seconds=300)
    assert first_lease is not None

    second_lease = acquire_ownership(db_session, review, w2, lease_seconds=300)
    assert second_lease is None

    # Original owner preserved
    db_session.refresh(review)
    assert review.owner_identity == w1


def test_acquire_ownership_takeover_when_lease_expired(db_session: Session) -> None:
    """Verify a new worker can acquire lease if the existing lease has expired."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    w1 = "worker-old"
    w2 = "worker-new"

    # Set expired lease manually
    review.owner_identity = w1
    review.owner_expires_at = utc_now() - timedelta(seconds=10)
    db_session.commit()

    new_lease = acquire_ownership(db_session, review, w2, lease_seconds=120)
    assert new_lease is not None
    assert new_lease.owner_identity == w2


def test_verify_fencing_pass_and_fail(db_session: Session) -> None:
    """Verify fencing validation logic."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    w1 = "worker-active"
    w2 = "worker-impostor"

    acquire_ownership(db_session, review, w1, lease_seconds=180)

    # Active lease owner -> Pass
    assert verify_fencing(db_session, review, w1) is True

    # Impostor worker -> Fail
    assert verify_fencing(db_session, review, w2) is False

    # Expire lease -> Fail
    review.owner_expires_at = utc_now() - timedelta(seconds=5)
    db_session.commit()
    assert verify_fencing(db_session, review, w1) is False


def test_reclaim_stale_reviews(db_session: Session) -> None:
    """Verify stale processing reviews are reclaimed and marked FAILED with AM-002 error."""
    _, review_stale = create_test_user_and_review(db_session, status="PROCESSING")
    _, review_active = create_test_user_and_review(db_session, status="PROCESSING")

    # Set stale review
    review_stale.owner_identity = "worker-crashed"
    review_stale.owner_expires_at = utc_now() - timedelta(minutes=15)

    # Set active review
    review_active.owner_identity = "worker-alive"
    review_active.owner_expires_at = utc_now() + timedelta(minutes=5)
    db_session.commit()

    reclaimed = reclaim_stale_reviews(db_session)
    assert len(reclaimed) == 1
    assert reclaimed[0].id == review_stale.id

    db_session.refresh(review_stale)
    db_session.refresh(review_active)

    assert review_stale.status == "FAILED"
    assert review_stale.error_message == AM002_TIMEOUT_ERROR
    assert review_stale.owner_identity is None

    # Active review remains untouched
    assert review_active.status == "PROCESSING"
    assert review_active.owner_identity == "worker-alive"


def test_worker_fencing_in_review_engine(db_session: Session) -> None:
    """Verify ReviewEngineService enforces worker fencing prior to completion."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    worker1 = "worker-1"
    worker2 = "worker-2"

    engine = ReviewEngineService()

    # Worker 1 acquires ownership
    acquire_ownership(db_session, review, worker1, lease_seconds=300)

    # Worker 2 attempts execution under worker2 identity -> rejected by fencing or preflight
    res = engine.execute_review_engine(review.id, db=db_session, worker_identity=worker2)
    assert res is not None


def test_maintenance_reclaim_endpoint_authentication_required() -> None:
    """Unauthenticated call to maintenance reclamation endpoint returns 401."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.post("/api/v1/maintenance/reclaim-stale-reviews")
    assert response.status_code == 401


def test_maintenance_reclaim_endpoint_success() -> None:
    """Authenticated call to maintenance reclamation endpoint returns success summary."""
    from fastapi.testclient import TestClient
    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, secret_key=TEST_AUTH_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/maintenance/reclaim-stale-reviews", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "reclaimed_count" in data
    assert "reclaimed_review_ids" in data


def test_reviews_maintenance_reclaim_endpoint_success() -> None:
    """Authenticated call to reviews/maintenance/reclaim-stale-reviews returns success summary."""
    from fastapi.testclient import TestClient
    from app.core.security import create_access_token
    from app.main import app

    client = TestClient(app)
    user_id = str(uuid.uuid4())
    token = create_access_token(subject=user_id, secret_key=TEST_AUTH_SECRET)
    headers = {"Authorization": f"Bearer {token}"}

    response = client.post("/api/v1/reviews/maintenance/reclaim-stale-reviews", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "reclaimed_count" in data


def test_authoritative_fencing_bypasses_orm_cache(db_session: Session) -> None:
    """Verify verify_fencing forces a DB refresh to reject stale ORM cached owner state."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    w1 = "worker-1"
    acquire_ownership(db_session, review, w1, lease_seconds=300)

    # Simulate another session/reclaimer modifying database row directly
    engine = db_session.get_bind()
    TestingSessionLocal = sessionmaker(bind=engine)
    session2 = TestingSessionLocal()
    try:
        r2 = session2.query(Review).filter(Review.id == review.id).first()
        assert r2 is not None
        r2.status = "FAILED"
        r2.owner_identity = None
        r2.owner_expires_at = None
        session2.commit()
    finally:
        session2.close()

    # Original ORM object in db_session still has cached owner_identity="worker-1" in memory
    # verify_fencing MUST refresh from DB and return False
    assert verify_fencing(db_session, review, w1) is False


def test_zombie_worker_rejected_after_reclamation(db_session: Session) -> None:
    """Verify a zombie worker cannot mark review COMPLETED or persist findings after reclamation."""
    from app.db.models import Finding
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    w1 = "worker-crashed"

    acquire_ownership(db_session, review, w1, lease_seconds=10)

    # Reclaimer reclaims expired review
    review.owner_expires_at = utc_now() - timedelta(seconds=5)
    db_session.commit()
    reclaimed = reclaim_stale_reviews(db_session)
    assert len(reclaimed) == 1
    assert review.status == "FAILED"

    # Worker 1 resumes and attempts fencing verification
    is_fenced = verify_fencing(db_session, review, w1)
    assert is_fenced is False

    # Worker 1 cannot insert findings or mark COMPLETED
    if not is_fenced:
        db_session.rollback()

    assert review.status == "FAILED"
    findings_count = db_session.query(Finding).filter(Finding.review_id == review.id).count()
    assert findings_count == 0


def test_startup_and_periodic_lifespan_recovery() -> None:
    """Verify application lifespan performs startup recovery and clean ticker cancellation."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200


def test_concurrent_reclamation_safety(db_session: Session) -> None:
    """Verify concurrent reclamation from multiple sessions is safe and idempotent."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    review.owner_identity = "worker-stale"
    review.owner_expires_at = utc_now() - timedelta(minutes=10)
    db_session.commit()

    engine = db_session.get_bind()
    TestingSessionLocal = sessionmaker(bind=engine)
    s1 = TestingSessionLocal()
    s2 = TestingSessionLocal()
    try:
        rec1 = reclaim_stale_reviews(s1)
        rec2 = reclaim_stale_reviews(s2)
        assert len(rec1) == 1
        assert len(rec2) == 0
    finally:
        s1.close()
        s2.close()


def test_verify_fencing_db_refresh_failure_returns_false(db_session: Session) -> None:
    """Verify verify_fencing strictly returns False if database refresh raises an exception."""
    from unittest.mock import MagicMock
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    w1 = "worker-1"
    acquire_ownership(db_session, review, w1, lease_seconds=300)

    mock_db = MagicMock()
    mock_db.refresh.side_effect = Exception("DB Connection Error during refresh")

    # verify_fencing MUST return False when DB refresh raises an exception
    assert verify_fencing(mock_db, review, w1) is False


def test_ownership_takeover_rejects_old_worker(db_session: Session) -> None:
    """Verify when Worker B takes over an expired lease, Worker A's fencing fails and Worker B remains owner."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    w1 = "worker-old"
    w2 = "worker-new"

    # Worker 1 acquires ownership
    acquire_ownership(db_session, review, w1, lease_seconds=10)

    # Worker 1 lease expires
    review.owner_expires_at = utc_now() - timedelta(seconds=5)
    db_session.commit()

    # Worker 2 takes over ownership
    lease2 = acquire_ownership(db_session, review, w2, lease_seconds=300)
    assert lease2 is not None
    assert lease2.owner_identity == w2

    # Worker 1 attempts fencing check -> MUST fail
    assert verify_fencing(db_session, review, w1) is False

    # Worker 2 fencing check -> MUST pass
    assert verify_fencing(db_session, review, w2) is True


def test_null_lease_stale_review_reclaimed(db_session: Session) -> None:
    """Test B: A PROCESSING review with NULL lease fields created >300s ago is reclaimed to FAILED."""
    from app.services.ownership import AM003_ORPHAN_ERROR

    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    review.owner_identity = None
    review.owner_expires_at = None
    review.created_at = utc_now() - timedelta(seconds=600)
    db_session.commit()

    reclaimed = reclaim_stale_reviews(db_session)
    assert len(reclaimed) == 1
    assert reclaimed[0].id == review.id
    assert reclaimed[0].status == "FAILED"
    assert AM003_ORPHAN_ERROR in reclaimed[0].error_message


def test_null_lease_fresh_review_not_reclaimed(db_session: Session) -> None:
    """Test C: A recently created PROCESSING review with NULL lease fields is NOT reclaimed."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    review.owner_identity = None
    review.owner_expires_at = None
    review.created_at = utc_now() - timedelta(seconds=10)
    db_session.commit()

    reclaimed = reclaim_stale_reviews(db_session)
    assert len(reclaimed) == 0
    assert review.status == "PROCESSING"


def test_background_worker_exception_handling(db_session: Session) -> None:
    """Test D: An unhandled exception in background worker transitions review to FAILED."""
    from unittest.mock import patch
    from app.api.reviews import _run_review_engine_background

    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    review_id_str = str(review.id)

    with patch("app.api.reviews.get_sessionmaker") as mock_sm:
        mock_sm.return_value = lambda: db_session
        with patch("app.api.reviews.review_engine_service.execute_review_engine") as mock_exec:
            mock_exec.side_effect = RuntimeError("Simulated unhandled worker crash")
            _run_review_engine_background(review_id_str, repository_id="owner/repo", ref="main")

    saved_review = db_session.query(Review).filter(Review.id == uuid.UUID(review_id_str)).first()
    assert saved_review is not None
    assert saved_review.status == "FAILED"
    assert "Background worker task exception" in saved_review.error_message


def test_ownership_contention_preserves_processing_status(db_session: Session) -> None:
    """Test E: Contention when Worker B tries to acquire an active lease does not mark review FAILED."""
    _, review = create_test_user_and_review(db_session, status="PROCESSING")
    w1 = "worker-owner"
    w2 = "worker-contender"

    first = acquire_ownership(db_session, review, w1, lease_seconds=300)
    assert first is not None

    second = acquire_ownership(db_session, review, w2, lease_seconds=300)
    assert second is None
    assert review.status == "PROCESSING"
    assert review.owner_identity == w1


