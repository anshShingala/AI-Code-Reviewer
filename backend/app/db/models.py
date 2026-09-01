import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.base import Base


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class User(Base):
    """User account entity."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    github_user_id = Column(String(255), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    github_connection = relationship(
        "GitHubConnection",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    reviews = relationship(
        "Review",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class GitHubConnection(Base):
    """GitHub OAuth connection entity linked to user."""

    __tablename__ = "github_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    github_user_id = Column(String(255), nullable=False)
    access_token_encrypted = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    user = relationship("User", back_populates="github_connection")


class Review(Base):
    """Review entity supporting AM-001 idempotency and AM-002 execution ownership & lifecycle."""

    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_reviews_user_idempotency"),
        Index("ix_reviews_user_id", "user_id"),
        Index("ix_reviews_status", "status"),
        Index("ix_reviews_owner_expires", "owner_expires_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(50), nullable=False, default="PROCESSING")
    owner_identity = Column(String(255), nullable=True)
    owner_expires_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    user = relationship("User", back_populates="reviews")
    review_files = relationship(
        "ReviewFile",
        back_populates="review",
        cascade="all, delete-orphan",
    )
    findings = relationship(
        "Finding",
        back_populates="review",
        cascade="all, delete-orphan",
    )


class ReviewFile(Base):
    """File target entry within a Review."""

    __tablename__ = "review_files"
    __table_args__ = (
        Index("ix_review_files_review_id", "review_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(
        UUID(as_uuid=True),
        ForeignKey("reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path = Column(String(1024), nullable=False)
    status = Column(String(50), nullable=False, default="PENDING")
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    review = relationship("Review", back_populates="review_files")


class Finding(Base):
    """Static and AI-generated review finding associated with a Review."""

    __tablename__ = "findings"
    __table_args__ = (
        Index("ix_findings_review_id", "review_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    review_id = Column(
        UUID(as_uuid=True),
        ForeignKey("reviews.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path = Column(String(1024), nullable=False)
    line_number = Column(Integer, nullable=False)
    severity = Column(String(50), nullable=False)
    category = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    review = relationship("Review", back_populates="findings")
