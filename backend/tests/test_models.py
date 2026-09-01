import pytest
from app.db.base import Base
from app.db.models import Finding, GitHubConnection, Review, ReviewFile, User


def test_five_application_tables_exist() -> None:
    """Verify that exactly the 5 frozen application tables exist in SQLAlchemy Base metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected_tables = {
        "users",
        "github_connections",
        "reviews",
        "review_files",
        "findings",
    }
    assert table_names == expected_tables, f"Expected exactly {expected_tables}, got {table_names}"


def test_users_table_schema() -> None:
    """Verify users table columns and constraints."""
    table = Base.metadata.tables["users"]
    col_names = {c.name for c in table.columns}
    expected_cols = {"id", "email", "github_user_id", "created_at", "updated_at"}
    assert col_names == expected_cols

    # Check unique constraint on email
    email_col = table.columns["email"]
    assert email_col.unique is True or any(
        c.name == "email" for idx in table.indexes if idx.unique for c in idx.columns
    )


def test_github_connections_table_schema() -> None:
    """Verify github_connections table columns and foreign keys."""
    table = Base.metadata.tables["github_connections"]
    col_names = {c.name for c in table.columns}
    expected_cols = {
        "id",
        "user_id",
        "github_user_id",
        "access_token_encrypted",
        "created_at",
        "updated_at",
    }
    assert col_names == expected_cols

    # Verify foreign key to users.id
    user_id_col = table.columns["user_id"]
    fk_targets = {fk.target_fullname for fk in user_id_col.foreign_keys}
    assert "users.id" in fk_targets


def test_reviews_table_am001_and_am002_schema() -> None:
    """Verify reviews table supports AM-001 idempotency and AM-002 execution ownership & lifecycle."""
    table = Base.metadata.tables["reviews"]
    col_names = {c.name for c in table.columns}
    expected_cols = {
        "id",
        "user_id",
        "idempotency_key",
        "request_hash",
        "status",
        "owner_identity",
        "owner_expires_at",
        "error_message",
        "created_at",
        "updated_at",
    }
    assert col_names == expected_cols

    # Verify unique constraint uq_reviews_user_idempotency (AM-001)
    uq_names = {uq.name for uq in table.constraints if hasattr(uq, "name")}
    assert "uq_reviews_user_idempotency" in uq_names


def test_review_files_table_schema() -> None:
    """Verify review_files table columns and foreign keys."""
    table = Base.metadata.tables["review_files"]
    col_names = {c.name for c in table.columns}
    expected_cols = {"id", "review_id", "file_path", "status", "created_at"}
    assert col_names == expected_cols

    review_id_col = table.columns["review_id"]
    fk_targets = {fk.target_fullname for fk in review_id_col.foreign_keys}
    assert "reviews.id" in fk_targets


def test_findings_table_schema() -> None:
    """Verify findings table columns and foreign keys."""
    table = Base.metadata.tables["findings"]
    col_names = {c.name for c in table.columns}
    expected_cols = {
        "id",
        "review_id",
        "file_path",
        "line_number",
        "severity",
        "category",
        "title",
        "message",
        "suggestion",
        "created_at",
    }
    assert col_names == expected_cols

    review_id_col = table.columns["review_id"]
    fk_targets = {fk.target_fullname for fk in review_id_col.foreign_keys}
    assert "reviews.id" in fk_targets
