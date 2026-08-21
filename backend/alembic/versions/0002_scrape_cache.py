"""scrape cache and source reliability (spec §53, Milestone 5)

Phase 5 reads the candidate pages, which costs credits per page — so the outcome of
every read is stored and reused. The same rows answer "which sources can actually
be read", which the milestone asks to be recorded rather than assumed.

Additive: no existing table is touched, so the upgrade is safe on a live database
and the downgrade only drops what this revision created.

Revision ID: 0002
Revises: 0001
Created: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scrape_cache",
        # A hash of the canonical URL, not the URL: profile links with query strings
        # would otherwise outgrow a btree index.
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("reader", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("profile", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        "ix_scrape_cache_platform_outcome", "scrape_cache", ["platform", "outcome"], unique=False
    )
    op.create_index(op.f("ix_scrape_cache_outcome"), "scrape_cache", ["outcome"], unique=False)
    op.create_index(
        op.f("ix_scrape_cache_last_scraped_at"), "scrape_cache", ["last_scraped_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_scrape_cache_last_scraped_at"), table_name="scrape_cache")
    op.drop_index(op.f("ix_scrape_cache_outcome"), table_name="scrape_cache")
    op.drop_index("ix_scrape_cache_platform_outcome", table_name="scrape_cache")
    op.drop_table("scrape_cache")
