import hashlib
import json
from typing import Any, List
import uuid

from fastapi import APIRouter, Header, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.models import Finding, Review, ReviewFile, User
from app.db.session import get_db
from app.services.github import GitHubService
from app.services.review_engine import ReviewEngineService
from app.api.github import _get_active_github_access_token

router = APIRouter(prefix="/reviews", tags=["reviews"])
github_service = GitHubService()
review_engine_service = ReviewEngineService(github_service=github_service)

ALLOWED_CATEGORIES = {"BUG", "SECURITY", "PERFORMANCE", "MAINTAINABILITY"}
ALLOWED_SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


class ReviewCreateRequest(BaseModel):
    repository_id: str = Field(..., description="Repository owner/repo identifier")
    ref: str = Field(..., description="Git branch or ref name")
    files: List[str] = Field(..., description="Selected file paths for review")
    categories: List[str] = Field(..., description="Review categories requested")


def compute_canonical_request_hash(
    repository_id: str,
    ref: str,
    files: List[str],
    categories: List[str],
) -> str:
    """Construct deterministic SHA-256 hash of canonical request semantic payload."""
    sorted_files = sorted(files)
    sorted_categories = sorted([c.upper() for c in categories])

    canonical_payload = {
        "categories": sorted_categories,
        "files": sorted_files,
        "ref": ref,
        "repository_id": repository_id,
    }

    canonical_json = json.dumps(canonical_payload, sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


_MOCK_REVIEWS_STORE: dict[tuple[str, str], dict[str, Any]] = {}


@router.post("", status_code=202)
def create_review(
    request_data: ReviewCreateRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> dict[str, Any]:
    """Create a Review request supporting AM-001 request-level idempotency."""
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )

    idempotency_key = idempotency_key.strip()

    # Validate repository_id format
    if "/" not in request_data.repository_id or request_data.repository_id.count("/") != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repository_id format. Expected 'owner/repo'.",
        )

    # Validate non-empty files
    if not request_data.files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="files list cannot be empty.",
        )

    # Validate categories taxonomy
    if not request_data.categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="categories list cannot be empty.",
        )

    normalized_categories = []
    for cat in request_data.categories:
        upper_cat = cat.upper()
        if upper_cat not in ALLOWED_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid review category '{cat}'. Allowed categories: BUG, SECURITY, PERFORMANCE, MAINTAINABILITY.",
            )
        normalized_categories.append(upper_cat)

    # Compute canonical request hash
    calculated_request_hash = compute_canonical_request_hash(
        repository_id=request_data.repository_id,
        ref=request_data.ref,
        files=request_data.files,
        categories=normalized_categories,
    )

    # Verify GitHub access and resolve exact commit SHA
    owner, repo = request_data.repository_id.split("/")
    access_token = _get_active_github_access_token(current_user, db)

    # In live mode (or when token is real), resolve ref to exact commit SHA
    resolved_sha = github_service.resolve_ref_to_sha(access_token, owner, repo, request_data.ref)

    if db is None:
        # Testing fallback store when DB is unready/testing
        mock_key = (str(current_user.id), idempotency_key)
        if mock_key in _MOCK_REVIEWS_STORE:
            existing = _MOCK_REVIEWS_STORE[mock_key]
            if existing["request_hash"] == calculated_request_hash:
                return existing
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key reuse with conflicting request payload.",
                )

        new_mock_review = {
            "id": str(uuid.uuid4()),
            "status": "PROCESSING",
            "idempotency_key": idempotency_key,
            "request_hash": calculated_request_hash,
            "created_at": "2026-09-01T00:00:00Z",
            "findings_count": 0,
            "files": [{"id": str(uuid.uuid4()), "file_path": f, "status": "PENDING"} for f in sorted(request_data.files)],
            "findings": [],
        }
        _MOCK_REVIEWS_STORE[mock_key] = new_mock_review
        return new_mock_review

    # Atomic DB Transaction & Idempotency Resolution
    existing_review = (
        db.query(Review)
        .filter(Review.user_id == current_user.id, Review.idempotency_key == idempotency_key)
        .first()
    )

    if existing_review:
        if existing_review.request_hash == calculated_request_hash:
            # Case 1: Equivalent Replay -> Return same Review
            return {
                "id": str(existing_review.id),
                "status": existing_review.status,
                "idempotency_key": existing_review.idempotency_key,
                "request_hash": existing_review.request_hash,
                "created_at": existing_review.created_at.isoformat(),
            }
        else:
            # Case 2: Conflicting Payload -> Return 409 Conflict
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key reuse with conflicting request payload.",
            )

    # Case 3: New Creation
    new_review = Review(
        id=uuid.uuid4(),
        user_id=current_user.id,
        idempotency_key=idempotency_key,
        request_hash=calculated_request_hash,
        status="PROCESSING",
    )
    db.add(new_review)

    for file_path in sorted(request_data.files):
        new_file = ReviewFile(
            id=uuid.uuid4(),
            review_id=new_review.id,
            file_path=file_path,
            status="PENDING",
        )
        db.add(new_file)

    try:
        db.commit()
        db.refresh(new_review)
        return {
            "id": str(new_review.id),
            "status": new_review.status,
            "idempotency_key": new_review.idempotency_key,
            "request_hash": new_review.request_hash,
            "created_at": new_review.created_at.isoformat(),
        }
    except IntegrityError:
        # Atomic race condition handling: concurrent request won the unique constraint
        db.rollback()
        winning_review = (
            db.query(Review)
            .filter(Review.user_id == current_user.id, Review.idempotency_key == idempotency_key)
            .first()
        )
        if winning_review:
            if winning_review.request_hash == calculated_request_hash:
                return {
                    "id": str(winning_review.id),
                    "status": winning_review.status,
                    "idempotency_key": winning_review.idempotency_key,
                    "request_hash": winning_review.request_hash,
                    "created_at": winning_review.created_at.isoformat(),
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key reuse with conflicting request payload.",
                )
        raise


@router.get("", status_code=200)
def list_reviews(
    status_param: str | None = Query(None, alias="status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> dict[str, Any]:
    """List authenticated user's review history sorted by created_at DESC."""
    if db is None:
        user_id_str = str(current_user.id)
        user_reviews = [
            v for (uid, key), v in _MOCK_REVIEWS_STORE.items()
            if uid == user_id_str
        ]
        if status_param:
            user_reviews = [r for r in user_reviews if r.get("status") == status_param.upper()]

        total = len(user_reviews)
        paginated = user_reviews[offset: offset + limit]
        formatted = []
        for r in paginated:
            formatted.append({
                "id": r["id"],
                "idempotency_key": r["idempotency_key"],
                "status": r["status"],
                "created_at": r["created_at"],
                "updated_at": r.get("created_at", "2026-09-01T00:00:00Z"),
                "findings_count": r.get("findings_count", 0),
            })
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "reviews": formatted,
        }

    query = db.query(Review).filter(Review.user_id == current_user.id)
    if status_param:
        query = query.filter(Review.status == status_param.upper())

    total = query.count()
    reviews = (
        query.order_by(Review.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    review_list = []
    for r in reviews:
        findings_count = db.query(Finding).filter(Finding.review_id == r.id).count()
        review_list.append({
            "id": str(r.id),
            "idempotency_key": r.idempotency_key,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
            "findings_count": findings_count,
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "reviews": review_list,
    }


@router.get("/{review_id}", status_code=200)
def get_review_detail(
    review_id: str,
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve detailed metadata and file status for a specific Review."""
    try:
        review_uuid = uuid.UUID(review_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid review_id format. Expected UUID.",
        )

    if db is None:
        user_id_str = str(current_user.id)
        for (uid, key), r in _MOCK_REVIEWS_STORE.items():
            if uid == user_id_str and r["id"] == str(review_uuid):
                return {
                    "id": r["id"],
                    "idempotency_key": r["idempotency_key"],
                    "status": r["status"],
                    "error_message": r.get("error_message"),
                    "created_at": r["created_at"],
                    "updated_at": r.get("created_at", "2026-09-01T00:00:00Z"),
                    "files": r.get("files", []),
                    "findings_count": r.get("findings_count", 0),
                }
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )

    review = (
        db.query(Review)
        .filter(Review.id == review_uuid, Review.user_id == current_user.id)
        .first()
    )
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )

    files = db.query(ReviewFile).filter(ReviewFile.review_id == review.id).all()
    findings_count = db.query(Finding).filter(Finding.review_id == review.id).count()

    return {
        "id": str(review.id),
        "idempotency_key": review.idempotency_key,
        "status": review.status,
        "error_message": review.error_message,
        "created_at": review.created_at.isoformat(),
        "updated_at": review.updated_at.isoformat(),
        "files": [
            {
                "id": str(f.id),
                "file_path": f.file_path,
                "status": f.status,
            }
            for f in files
        ],
        "findings_count": findings_count,
    }


@router.get("/{review_id}/findings", status_code=200)
def get_review_findings(
    review_id: str,
    file_path: str | None = Query(None),
    category: str | None = Query(None),
    severity: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> dict[str, Any]:
    """Query and filter validated findings associated with a specific Review."""
    try:
        review_uuid = uuid.UUID(review_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid review_id format. Expected UUID.",
        )

    if category:
        upper_cat = category.upper()
        if upper_cat not in ALLOWED_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid category '{category}'. Allowed categories: BUG, SECURITY, PERFORMANCE, MAINTAINABILITY.",
            )

    if severity:
        upper_sev = severity.upper()
        if upper_sev not in ALLOWED_SEVERITIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid severity '{severity}'. Allowed severities: CRITICAL, HIGH, MEDIUM, LOW.",
            )

    if db is None:
        user_id_str = str(current_user.id)
        found_review = None
        for (uid, key), r in _MOCK_REVIEWS_STORE.items():
            if uid == user_id_str and r["id"] == str(review_uuid):
                found_review = r
                break
        if not found_review:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found.",
            )

        findings_list = found_review.get("findings", [])
        if file_path:
            findings_list = [f for f in findings_list if f["file_path"] == file_path]
        if category:
            findings_list = [f for f in findings_list if f["category"] == category.upper()]
        if severity:
            findings_list = [f for f in findings_list if f["severity"] == severity.upper()]

        return {
            "review_id": str(review_uuid),
            "status": found_review["status"],
            "total_findings": len(findings_list),
            "findings": findings_list,
        }

    review = (
        db.query(Review)
        .filter(Review.id == review_uuid, Review.user_id == current_user.id)
        .first()
    )
    if not review:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )

    query = db.query(Finding).filter(Finding.review_id == review.id)
    if file_path:
        query = query.filter(Finding.file_path == file_path)
    if category:
        query = query.filter(Finding.category == category.upper())
    if severity:
        query = query.filter(Finding.severity == severity.upper())

    findings = query.order_by(Finding.created_at.asc()).all()

    return {
        "review_id": str(review.id),
        "status": review.status,
        "total_findings": len(findings),
        "findings": [
            {
                "id": str(f.id),
                "file_path": f.file_path,
                "line_number": f.line_number,
                "severity": f.severity,
                "category": f.category,
                "title": f.title,
                "message": f.message,
                "suggestion": f.suggestion,
                "created_at": f.created_at.isoformat(),
            }
            for f in findings
        ],
    }


class ReviewCreateRequest(BaseModel):
    repository_id: str = Field(..., description="Repository owner/repo identifier")
    ref: str = Field(..., description="Git branch or ref name")
    files: List[str] = Field(..., description="Selected file paths for review")
    categories: List[str] = Field(..., description="Review categories requested")


def compute_canonical_request_hash(
    repository_id: str,
    ref: str,
    files: List[str],
    categories: List[str],
) -> str:
    """Construct deterministic SHA-256 hash of canonical request semantic payload."""
    sorted_files = sorted(files)
    sorted_categories = sorted([c.upper() for c in categories])

    canonical_payload = {
        "categories": sorted_categories,
        "files": sorted_files,
        "ref": ref,
        "repository_id": repository_id,
    }

    canonical_json = json.dumps(canonical_payload, sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


_MOCK_REVIEWS_STORE: dict[tuple[str, str], dict[str, Any]] = {}


@router.post("", status_code=202)
def create_review(
    request_data: ReviewCreateRequest,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    db: Session | None = Depends(get_db),
) -> dict[str, Any]:
    """Create a Review request supporting AM-001 request-level idempotency."""
    if not idempotency_key or not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )

    idempotency_key = idempotency_key.strip()

    # Validate repository_id format
    if "/" not in request_data.repository_id or request_data.repository_id.count("/") != 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid repository_id format. Expected 'owner/repo'.",
        )

    # Validate non-empty files
    if not request_data.files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="files list cannot be empty.",
        )

    # Validate categories taxonomy
    if not request_data.categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="categories list cannot be empty.",
        )

    normalized_categories = []
    for cat in request_data.categories:
        upper_cat = cat.upper()
        if upper_cat not in ALLOWED_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid review category '{cat}'. Allowed categories: BUG, SECURITY, PERFORMANCE, MAINTAINABILITY.",
            )
        normalized_categories.append(upper_cat)

    # Compute canonical request hash
    calculated_request_hash = compute_canonical_request_hash(
        repository_id=request_data.repository_id,
        ref=request_data.ref,
        files=request_data.files,
        categories=normalized_categories,
    )

    # Verify GitHub access and resolve exact commit SHA
    owner, repo = request_data.repository_id.split("/")
    access_token = _get_active_github_access_token(current_user, db)

    # In live mode (or when token is real), resolve ref to exact commit SHA
    resolved_sha = github_service.resolve_ref_to_sha(access_token, owner, repo, request_data.ref)

    if db is None:
        # Testing fallback store when DB is unready/testing
        mock_key = (str(current_user.id), idempotency_key)
        if mock_key in _MOCK_REVIEWS_STORE:
            existing = _MOCK_REVIEWS_STORE[mock_key]
            if existing["request_hash"] == calculated_request_hash:
                return existing
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key reuse with conflicting request payload.",
                )

        new_mock_review = {
            "id": str(uuid.uuid4()),
            "status": "PROCESSING",
            "idempotency_key": idempotency_key,
            "request_hash": calculated_request_hash,
            "created_at": "2026-09-01T00:00:00Z",
        }
        _MOCK_REVIEWS_STORE[mock_key] = new_mock_review
        return new_mock_review

    # Atomic DB Transaction & Idempotency Resolution
    existing_review = (
        db.query(Review)
        .filter(Review.user_id == current_user.id, Review.idempotency_key == idempotency_key)
        .first()
    )

    if existing_review:
        if existing_review.request_hash == calculated_request_hash:
            # Case 1: Equivalent Replay -> Return same Review
            return {
                "id": str(existing_review.id),
                "status": existing_review.status,
                "idempotency_key": existing_review.idempotency_key,
                "request_hash": existing_review.request_hash,
                "created_at": existing_review.created_at.isoformat(),
            }
        else:
            # Case 2: Conflicting Payload -> Return 409 Conflict
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key reuse with conflicting request payload.",
            )

    # Case 3: New Creation
    new_review = Review(
        id=uuid.uuid4(),
        user_id=current_user.id,
        idempotency_key=idempotency_key,
        request_hash=calculated_request_hash,
        status="PROCESSING",
    )
    db.add(new_review)

    for file_path in sorted(request_data.files):
        new_file = ReviewFile(
            id=uuid.uuid4(),
            review_id=new_review.id,
            file_path=file_path,
            status="PENDING",
        )
        db.add(new_file)

    try:
        db.commit()
        db.refresh(new_review)
        return {
            "id": str(new_review.id),
            "status": new_review.status,
            "idempotency_key": new_review.idempotency_key,
            "request_hash": new_review.request_hash,
            "created_at": new_review.created_at.isoformat(),
        }
    except IntegrityError:
        # Atomic race condition handling: concurrent request won the unique constraint
        db.rollback()
        winning_review = (
            db.query(Review)
            .filter(Review.user_id == current_user.id, Review.idempotency_key == idempotency_key)
            .first()
        )
        if winning_review:
            if winning_review.request_hash == calculated_request_hash:
                return {
                    "id": str(winning_review.id),
                    "status": winning_review.status,
                    "idempotency_key": winning_review.idempotency_key,
                    "request_hash": winning_review.request_hash,
                    "created_at": winning_review.created_at.isoformat(),
                }
            else:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key reuse with conflicting request payload.",
                )
        raise
