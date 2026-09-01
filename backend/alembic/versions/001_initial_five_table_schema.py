"""Initial 5-table schema migration

Revision ID: 001_initial_five_table_schema
Revises:
Create Date: 2026-08-31

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial_five_table_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('github_user_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('email', name='uq_users_email'),
        sa.UniqueConstraint('github_user_id', name='uq_users_github_user_id'),
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

    # 2. github_connections table
    op.create_table(
        'github_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('github_user_id', sa.String(length=255), nullable=False),
        sa.Column('access_token_encrypted', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_github_connections_user_id'),
        sa.UniqueConstraint('user_id', name='uq_github_connections_user_id'),
    )
    op.create_index('ix_github_connections_user_id', 'github_connections', ['user_id'], unique=True)

    # 3. reviews table (AM-001 idempotency & AM-002 execution ownership / lifecycle)
    op.create_table(
        'reviews',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('owner_identity', sa.String(length=255), nullable=True),
        sa.Column('owner_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE', name='fk_reviews_user_id'),
        sa.UniqueConstraint('user_id', 'idempotency_key', name='uq_reviews_user_idempotency'),
    )
    op.create_index('ix_reviews_user_id', 'reviews', ['user_id'], unique=False)
    op.create_index('ix_reviews_status', 'reviews', ['status'], unique=False)
    op.create_index('ix_reviews_owner_expires', 'reviews', ['owner_expires_at'], unique=False)

    # 4. review_files table
    op.create_table(
        'review_files',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE', name='fk_review_files_review_id'),
    )
    op.create_index('ix_review_files_review_id', 'review_files', ['review_id'], unique=False)

    # 5. findings table
    op.create_table(
        'findings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('review_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_path', sa.String(length=1024), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=False),
        sa.Column('severity', sa.String(length=50), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('suggestion', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['review_id'], ['reviews.id'], ondelete='CASCADE', name='fk_findings_review_id'),
    )
    op.create_index('ix_findings_review_id', 'findings', ['review_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_findings_review_id', table_name='findings')
    op.drop_table('findings')

    op.drop_index('ix_review_files_review_id', table_name='review_files')
    op.drop_table('review_files')

    op.drop_index('ix_reviews_owner_expires', table_name='reviews')
    op.drop_index('ix_reviews_status', table_name='reviews')
    op.drop_index('ix_reviews_user_id', table_name='reviews')
    op.drop_table('reviews')

    op.drop_index('ix_github_connections_user_id', table_name='github_connections')
    op.drop_table('github_connections')

    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')
