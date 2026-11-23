"""a refusal's explanation as a code, so it can be shown in the client's language

`detail` is an English sentence written where the refusal happens; the interface
is Ukrainian, Russian or English. `detail_code` and `detail_params` carry the same
explanation as data, and the interface words it.

Additive: existing rows keep their English `detail` and get an empty code.

Revision ID: 0006
Revises: 0005
Created: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "search_rejections",
        sa.Column("detail_code", sa.String(length=48), nullable=False, server_default=""),
    )
    op.add_column(
        "search_rejections",
        sa.Column(
            "detail_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("search_rejections", "detail_params")
    op.drop_column("search_rejections", "detail_code")
