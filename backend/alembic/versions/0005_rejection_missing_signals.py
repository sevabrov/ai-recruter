"""which signals a refusal is about, and the posts a candidate was found through

"Missing a required signal" on its own does not say which one, and the client
had to read an English sentence to find out. `missing` stores the list.

A post whose author was judged is no longer a refusal of its own: it is evidence
on the author's row, listed in `found_via`.

Additive: both columns default to an empty list.

Revision ID: 0005
Revises: 0004
Created: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("missing", "found_via"):
        op.add_column(
            "search_rejections",
            sa.Column(
                column,
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )


def downgrade() -> None:
    op.drop_column("search_rejections", "found_via")
    op.drop_column("search_rejections", "missing")
