"""who published a refused post, and what became of them

A refused post read as a lost person: "not a profile" next to a reel titled "Why
network marketing?". The run had in fact followed the post to its author and
judged them — but nothing on the post's row said so. These columns say it.

Additive and nullable: existing rows simply have no author recorded.

Revision ID: 0004
Revises: 0003
Created: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("search_rejections", sa.Column("author_url", sa.Text(), nullable=True))
    op.add_column(
        "search_rejections",
        sa.Column("author_name", sa.String(length=300), nullable=False, server_default=""),
    )
    op.add_column(
        "search_rejections", sa.Column("author_outcome", sa.String(length=32), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("search_rejections", "author_outcome")
    op.drop_column("search_rejections", "author_name")
    op.drop_column("search_rejections", "author_url")
