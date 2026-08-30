"""the candidates a search turned away (spec §43)

A run reported how many candidates each requirement refused, and nothing more. The
counts are not checkable: the only way to answer "are we losing leads in there?" is
to be able to open the addresses. This table stores one row per refused candidate,
so the results screen can show the two lists side by side.

Additive: no existing table is touched, so the upgrade is safe on a live database
and the downgrade only drops what this revision created. Searches recorded before
it simply have no rows, which the API reports as an empty second list.

Revision ID: 0003
Revises: 0002
Created: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `progress.rejectedUnreadable` needs no migration: progress is a document,
    # and a search recorded before this revision simply has no such key.
    op.create_table(
        "search_rejections",
        sa.Column("id", sa.String(length=160), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("search_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        # Whether the page itself was ever opened: the difference between a
        # candidate judged on what they published and one judged on two lines of
        # search result.
        sa.Column("read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("promise", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["search_id"], ["searches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_search_rejections_search_reason",
        "search_rejections",
        ["search_id", "reason"],
        unique=False,
    )
    op.create_index(
        op.f("ix_search_rejections_search_id"), "search_rejections", ["search_id"], unique=False
    )
    op.create_index(
        op.f("ix_search_rejections_user_id"), "search_rejections", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_search_rejections_user_id"), table_name="search_rejections")
    op.drop_index(op.f("ix_search_rejections_search_id"), table_name="search_rejections")
    op.drop_index("ix_search_rejections_search_reason", table_name="search_rejections")
    op.drop_table("search_rejections")
